# -*- coding: utf-8 -*-
"""
app.agent_base

Generic, extensible agent that serves every role-specific AI worker.
This is a vanilla "base agent", can be launched by instantiating **AgentBase**
with default arguments; specialised agents simply subclass and override
or extend the protected hooks.

CraftBot is an open-source, light version of AI agent developed by CraftOS.
Here are the core features:
- Todo-based task tracking
- Can switch between CLI/GUI mode

Main agent cycle:
- Receive query from user
- Reply or create task
- Task cycle:
    - Action selection and execution
    - Update todos
    - Repeat until completion
"""

from __future__ import annotations

import asyncio
import os
import traceback
import time
import uuid
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_core import Action

from agent_core import ActionLibrary, ActionManager, ActionRouter

from app.config import (
    AGENT_WORKSPACE_ROOT,
    AGENT_FILE_SYSTEM_PATH,
    AGENT_MEMORY_CHROMA_PATH,
    PROCESS_MEMORY_AT_STARTUP,
    MEMORY_PROCESSING_SCHEDULE_HOUR,
)

from app.tui import TUIInterface
from app.internal_action_interface import InternalActionInterface
from app.llm import LLMInterface, LLMCallType
from app.vlm_interface import VLMInterface
from app.database_interface import DatabaseInterface
from app.logger import logger
from agent_core import MemoryManager, MemoryPointer, MemoryFileWatcher, create_memory_processing_task
from app.context_engine import ContextEngine
from app.state.state_manager import StateManager
from app.state.agent_state import STATE
from app.trigger import Trigger, TriggerQueue
from app.prompt import ROUTE_TO_SESSION_PROMPT
from app.state.types import ReasoningResult
from app.task.task_manager import TaskManager
from app.event_stream import EventStreamManager
from app.gui.gui_module import GUIModule
from app.gui.handler import GUIHandler
from agent_core import profile, profile_loop, OperationCategory
from agent_core import (
    # Registries for dependency injection
    DatabaseRegistry,
    LLMInterfaceRegistry,
    EventStreamManagerRegistry,
    StateManagerRegistry,
    ContextEngineRegistry,
    ActionExecutorRegistry,
    ActionManagerRegistry,
    TaskManagerRegistry,
    MemoryRegistry,
)
from pathlib import Path


@dataclass
class AgentCommand:
    name: str
    description: str
    handler: Callable[[], Awaitable[str | None]]


@dataclass
class TriggerData:
    """Structured data extracted from a Trigger."""
    query: str
    gui_mode: bool | None
    parent_id: str | None
    session_id: str | None = None

class AgentBase:
    """
    Foundation class for all agents.

    Sub-classes typically override **one or more** of the following:

    * `_load_extra_system_prompt`     → inject role-specific prompt fragment
    * `_register_extra_actions`       → register additional tools
    * `_build_db_interface`           → point to another Mongo/Chroma DB
    """

    def __init__(
        self,
        *,
        data_dir: str = "app/data",
        chroma_path: str = "./chroma_db",
        llm_provider: str = "anthropic",
        deferred_init: bool = False,
    ) -> None:
        """
        This constructor that initializes all agent components.

        Args:
            data_dir: Filesystem path where persistent agent data (plans,
                history, etc.) is stored.
            chroma_path: Directory for the local Chroma vector store used by the
                RAG components.
            llm_provider: Provider name passed to :class:`LLMInterface` and
                :class:`VLMInterface`.
            deferred_init: If True, allow LLM/VLM initialization to be deferred
                until API key is configured (useful for first-time setup).
        """

        # persistence & memory
        self.db_interface = self._build_db_interface(
            data_dir = data_dir, chroma_path=chroma_path
        )

        # LLM + prompt plumbing (may be deferred if API key not yet configured)
        self.llm = LLMInterface(
            provider=llm_provider,
            db_interface=self.db_interface,
            deferred=deferred_init,
        )
        self.vlm = VLMInterface(provider=llm_provider, deferred=deferred_init)

        self.event_stream_manager = EventStreamManager(
            self.llm,
            agent_file_system_path=AGENT_FILE_SYSTEM_PATH
        )
        
        # action & task layers
        self.action_library = ActionLibrary(self.llm, db_interface=self.db_interface)

        self.triggers = TriggerQueue(
            llm=self.llm,
            route_to_session_prompt=ROUTE_TO_SESSION_PROMPT,
        )

        # global state
        self.state_manager = StateManager(
            self.event_stream_manager
        )
        self.context_engine = ContextEngine(state_manager=self.state_manager)
        self.context_engine.set_role_info_hook(self._generate_role_info_prompt)

        self.action_manager = ActionManager(
            self.action_library, self.llm, self.db_interface, self.event_stream_manager, self.context_engine, self.state_manager
        )
        self.action_router = ActionRouter(self.action_library, self.llm, self.context_engine)

        self.task_manager = TaskManager(
            db_interface=self.db_interface,
            event_stream_manager=self.event_stream_manager,
            state_manager=self.state_manager,
            llm_interface=self.llm,
            context_engine=self.context_engine,
            on_task_end_callback=self._cleanup_session_triggers,
        )

        # Bind task_manager so state_manager can look up tasks by session_id
        self.state_manager.bind_task_manager(self.task_manager)
        # Bind task_manager and event_stream_manager to trigger queue for rich routing context
        self.triggers.set_task_manager(self.task_manager)
        self.triggers.set_event_stream_manager(self.event_stream_manager)

        # Clean up any leftover temp directories from previous runs
        self.task_manager.cleanup_all_temp_dirs()

        # ── memory manager for proactive agent ──
        self.memory_manager = MemoryManager(
            agent_file_system_path=str(AGENT_FILE_SYSTEM_PATH),
            chroma_path=str(AGENT_MEMORY_CHROMA_PATH),
        )
        # Connect memory manager to context engine for memory-aware prompts
        self.context_engine.set_memory_manager(self.memory_manager)

        # ── Register components with shared registries ──
        # This enables shared code to access components via get_*() functions
        DatabaseRegistry.register(lambda: self.db_interface)
        LLMInterfaceRegistry.register(lambda: self.llm)
        EventStreamManagerRegistry.register(lambda: self.event_stream_manager)
        StateManagerRegistry.register(lambda: self.state_manager)
        ContextEngineRegistry.register(lambda: self.context_engine)
        TaskManagerRegistry.register(lambda: self.task_manager)
        ActionManagerRegistry.register(lambda: self.action_manager)
        MemoryRegistry.register(lambda: self.memory_manager)

        # Index the agent file system on startup (incremental)
        try:
            self.memory_manager.update()
        except Exception as e:
            logger.warning(f"[MEMORY] Failed to update memory index on startup: {e}")

        # Start file watcher to auto-index on changes
        self.memory_file_watcher = MemoryFileWatcher(
            memory_manager=self.memory_manager,
            debounce_seconds=30.0,
        )
        self.memory_file_watcher.start()


        InternalActionInterface.initialize(
            self.llm,
            self.task_manager,
            self.state_manager,
            vlm_interface=self.vlm,
            memory_manager=self.memory_manager,
            context_engine=self.context_engine,
        )

        # Initialize footage callback (will be set by TUI interface later)
        self._tui_footage_callback = None

        # Only initialize GUIModule if GUI mode is globally enabled
        gui_globally_enabled = os.getenv("GUI_MODE_ENABLED", "True") == "True"
        if gui_globally_enabled:
            GUIHandler.gui_module: GUIModule = GUIModule(
                provider=llm_provider,
                action_library=self.action_library,
                action_router=self.action_router,
                context_engine=self.context_engine,
                action_manager=self.action_manager,
                event_stream_manager=self.event_stream_manager,
                tui_footage_callback=self._tui_footage_callback,
            )
            # Set gui_module reference in InternalActionInterface for GUI event stream integration
            InternalActionInterface.gui_module = GUIHandler.gui_module
        else:
            GUIHandler.gui_module = None
            InternalActionInterface.gui_module = None
            logger.info("[AGENT] GUI mode disabled - skipping GUIModule initialization")

        # ── misc ──
        self.is_running: bool = True
        self._extra_system_prompt: str = self._load_extra_system_prompt()

        # Background scheduler task for daily memory processing
        self._memory_scheduler_task: Optional["asyncio.Task"] = None

        self._command_registry: Dict[str, AgentCommand] = {}
        self._register_builtin_commands()

    # =====================================
    # Commands
    # =====================================

    def _register_builtin_commands(self) -> None:
        self.register_command(
            "/reset",
            "Reset the agent state, clearing tasks, triggers, and session data.",
            self.reset_agent_state,
        )
        self.register_command(
            "/onboarding",
            "Re-run the user profile interview to update your preferences.",
            self._handle_onboarding_command,
        )

    def register_command(
        self,
        name: str,
        description: str,
        handler: Callable[[], Awaitable[str | None]],
    ) -> None:
        """
        Register an in-band command that users can invoke from chat.

        Commands are simple hooks (e.g. ``/reset``) that map to coroutine
        handlers. They are surfaced in the UI and routed via
        :meth:`get_commands`.

        Args:
            name: Command string the user types; case-insensitive.
            description: Human-readable description used in help menus.
            handler: Awaitable callable that performs the command action and
                returns an optional message to display.
        """

        self._command_registry[name.lower()] = AgentCommand(
            name=name.lower(), description=description, handler=handler
        )

    def get_commands(self) -> Dict[str, AgentCommand]:
        """Return all registered commands."""

        return self._command_registry

    # =====================================
    # Main Agent Cycle
    # =====================================
    @profile_loop
    async def react(self, trigger: Trigger) -> None:
        """
        Main agent cycle - routes to appropriate workflow handler.

        This method handles 4 distinct workflows:
        1. MEMORY: Background memory processing tasks
        2. GUI TASK: Visual interaction with screen elements
        3. COMPLEX TASK: Multi-step tasks with todo management
        4. SIMPLE TASK: Quick tasks that auto-complete
        5. CONVERSATION: No active task, handle user messages

        Args:
            trigger: The Trigger that wakes the agent up and describes
                when and why the agent should act.
        """
        session_id = trigger.session_id

        try:
            logger.debug("[REACT] starting...")

            # ----- WORKFLOW 1: Special Processing (memory, proactive, onbaording, etc) -----
            if self._is_memory_trigger(trigger):
                task_created = await self._handle_memory_workflow(trigger)
                if not task_created:
                    return  # No events to process

            # Initialize session for all other workflows
            trigger_data: TriggerData = self._extract_trigger_data(trigger)
            await self._initialize_session(trigger_data.gui_mode, session_id)

            # Record user message if routed from existing session via triggers.fire()
            # This ensures the LLM sees the user message in the event stream
            user_message = self._extract_user_message_from_trigger(trigger)
            if user_message:
                logger.info(f"[REACT] Recording routed user message: {user_message[:50]}...")
                self.state_manager.record_user_message(user_message)

            # Debug: Log state after session initialization
            logger.debug(
                f"[STATE] session_id={session_id} | "
                f"current_task_id={STATE.get_agent_property('current_task_id')} | "
                f"current_task={STATE.current_task.id if STATE.current_task else None}"
            )

            # ----- WORKFLOW 2: GUI Task Mode -----
            if self._is_gui_task_mode(session_id):
                await self._handle_gui_task_workflow(trigger_data, session_id)
                return

            # ----- WORKFLOW 3: Complex Task Mode -----
            if self._is_complex_task_mode(session_id):
                await self._handle_complex_task_workflow(trigger_data, session_id)
                return

            # ----- WORKFLOW 4: Simple Task Mode -----
            if self._is_simple_task_mode(session_id):
                await self._handle_simple_task_workflow(trigger_data, session_id)
                return

            # ----- WORKFLOW 5: Conversation Mode (default) -----
            await self._handle_conversation_workflow(trigger_data, session_id)

        except Exception as e:
            await self._handle_react_error(e, None, session_id, {})
        finally:
            self._cleanup_session()

    # =====================================
    # Memory Processing
    # =====================================

    def create_process_memory_task(self) -> str:
        """
        Create a task to process unprocessed events and move them to memory.

        This creates a task that uses the 'memory-processor' skill to guide
        the agent through:
        1. Read EVENT_UNPROCESSED.md for unprocessed events
        2. Evaluate event importance for long-term memory
        3. Check for duplicate memories using memory_search
        4. Write important, unique events to MEMORY.md
        5. Clear processed events from EVENT_UNPROCESSED.md

        Returns:
            The task ID of the created task.
        """
        logger.info("[MEMORY] Creating process memory task")

        # Enable skip_unprocessed_logging to prevent infinite loops
        # (events generated during memory processing won't be added to EVENT_UNPROCESSED.md)
        # This flag is automatically reset when the task ends (in task_manager._end_task)
        self.event_stream_manager.set_skip_unprocessed_logging(True)

        # Create task using the memory-processor skill
        task_id = create_memory_processing_task(self.task_manager)
        logger.info(f"[MEMORY] Process memory task created: {task_id}")

        return task_id

    async def _process_memory_at_startup(self) -> None:
        """
        Process unprocessed events into memory at startup.

        This checks if there are unprocessed events and fires a memory
        processing trigger if needed. The trigger goes through normal
        processing flow which creates the task and executes it.
        """
        import time

        try:
            unprocessed_file = AGENT_FILE_SYSTEM_PATH / "EVENT_UNPROCESSED.md"
            if not unprocessed_file.exists():
                logger.debug("[MEMORY] EVENT_UNPROCESSED.md not found, skipping startup processing")
                return

            # Check if there are events to process (more than just headers)
            content = unprocessed_file.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            # Filter out empty lines and header lines (starting with # or empty)
            event_lines = [l for l in lines if l.strip() and l.strip().startswith("[")]

            if not event_lines:
                logger.info("[MEMORY] No unprocessed events found at startup")
                return

            logger.info(f"[MEMORY] Found {len(event_lines)} unprocessed events at startup, firing processing trigger")

            # Fire a memory_processing trigger (not scheduled, so won't reschedule)
            trigger = Trigger(
                fire_at=time.time(),
                priority=50,
                next_action_description="Process unprocessed events into long-term memory (startup)",
                payload={
                    "type": "memory_processing",
                    "scheduled": False,  # Don't reschedule after this
                },
                session_id="memory_processing_startup",
            )
            await self.triggers.put(trigger)

        except Exception as e:
            logger.warning(f"[MEMORY] Failed to process memory at startup: {e}")

    async def _schedule_daily_memory_processing(self) -> None:
        """
        Start a background scheduler for daily memory processing.

        Instead of creating a future-dated trigger that sits in the queue,
        this launches an asyncio task that sleeps until the scheduled hour
        and only then creates the trigger. This prevents the memory_processing_daily
        session from appearing as "ACTIVE" when it's not actually running.
        """
        # Cancel any existing scheduler task
        if self._memory_scheduler_task and not self._memory_scheduler_task.done():
            self._memory_scheduler_task.cancel()
            try:
                await self._memory_scheduler_task
            except asyncio.CancelledError:
                pass

        # Start the background scheduler
        self._memory_scheduler_task = asyncio.create_task(
            self._memory_processing_scheduler_loop()
        )
        logger.debug("[MEMORY] Started background memory processing scheduler")

    async def _memory_processing_scheduler_loop(self) -> None:
        """
        Background scheduler loop that waits until the scheduled hour
        and then fires the memory processing trigger.

        This runs continuously, sleeping until the next scheduled time,
        firing the trigger, and then rescheduling for the next day.
        """
        from datetime import datetime, timedelta

        while self.is_running:
            try:
                now = datetime.now()
                # Calculate next occurrence of the scheduled hour
                scheduled_time = now.replace(
                    hour=MEMORY_PROCESSING_SCHEDULE_HOUR,
                    minute=0,
                    second=0,
                    microsecond=0
                )

                # If the scheduled time has already passed today, schedule for tomorrow
                if scheduled_time <= now:
                    scheduled_time += timedelta(days=1)

                sleep_seconds = (scheduled_time - now).total_seconds()
                logger.info(
                    f"[MEMORY] Scheduler sleeping until "
                    f"{scheduled_time.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"(in {sleep_seconds / 3600:.1f} hours)"
                )

                # Sleep until the scheduled time
                await asyncio.sleep(sleep_seconds)

                # Time to fire! Create an immediate trigger
                logger.info("[MEMORY] Scheduler woke up, firing memory processing trigger")
                trigger = Trigger(
                    fire_at=time.time(),  # Fire immediately
                    priority=100,  # Low priority - background task
                    next_action_description="Process unprocessed events into long-term memory (daily scheduled task)",
                    payload={
                        "type": "memory_processing",
                        "scheduled": True,
                    },
                    session_id="memory_processing_daily",
                )
                await self.triggers.put(trigger)

                # Small delay before rescheduling to ensure we're past the current minute
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.debug("[MEMORY] Memory processing scheduler cancelled")
                break
            except Exception as e:
                logger.warning(f"[MEMORY] Scheduler error: {e}, will retry in 1 hour")
                await asyncio.sleep(3600)  # Retry in 1 hour on error

    async def _handle_memory_processing_trigger(self) -> bool:
        """
        Handle the memory processing trigger.

        This is called when a memory processing trigger fires (startup or scheduled).
        It creates a task to process unprocessed events.

        Note: Rescheduling is handled automatically by the background scheduler loop
        (_memory_processing_scheduler_loop), so this method doesn't need to reschedule.

        Returns:
            True if a task was created and processing should continue,
            False if no task was created and react() should return.
        """
        logger.info("[MEMORY] Memory processing trigger fired")
        task_created = False

        try:
            # Check if there are events to process
            unprocessed_file = AGENT_FILE_SYSTEM_PATH / "EVENT_UNPROCESSED.md"
            if unprocessed_file.exists():
                content = unprocessed_file.read_text(encoding="utf-8")
                lines = content.strip().split("\n")
                event_lines = [l for l in lines if l.strip() and l.strip().startswith("[")]

                if event_lines:
                    logger.info(f"[MEMORY] Processing {len(event_lines)} unprocessed events")
                    self.create_process_memory_task()
                    task_created = True
                else:
                    logger.info("[MEMORY] No unprocessed events to process")
            else:
                logger.debug("[MEMORY] EVENT_UNPROCESSED.md not found")

        except Exception as e:
            logger.warning(f"[MEMORY] Failed to process memory: {e}")

        return task_created

    # =====================================
    # Workflow Routing
    # =====================================

    def _extract_trigger_data(self, trigger: Trigger) -> TriggerData:
        """Extract and structure data from trigger."""
        return TriggerData(
            query=trigger.next_action_description,
            gui_mode=trigger.payload.get("gui_mode"),
            parent_id=trigger.payload.get("parent_action_id"),
            session_id=trigger.session_id,
        )

    def _extract_user_message_from_trigger(self, trigger: Trigger) -> Optional[str]:
        """Extract user message that was appended by triggers.fire().

        When a message is routed to an existing session, the fire() method
        appends it as '[NEW USER MESSAGE]: {message}' to next_action_description.
        This message needs to be recorded to the event stream so the LLM can see it.

        Returns:
            The user message if found, None otherwise.
        """
        marker = "[NEW USER MESSAGE]:"
        desc = trigger.next_action_description
        if marker in desc:
            idx = desc.index(marker) + len(marker)
            return desc[idx:].strip()
        return None

    async def _initialize_session(self, gui_mode: bool | None, session_id: str) -> None:
        """Initialize the agent session and set current task ID.

        Note: Only sets current_task_id if no task is running for THIS session,
        since create_task() already sets the task_id which must be used for
        session cache lookups.
        """
        if not self.state_manager.is_running_task(session_id):
            STATE.set_agent_property("current_task_id", session_id)
        await self.state_manager.start_session(gui_mode, session_id=session_id)

    # ----- Mode Checks -----

    def _is_memory_trigger(self, trigger: Trigger) -> bool:
        """Check if trigger is for memory processing."""
        return trigger.payload.get("type") == "memory_processing"

    def _is_gui_task_mode(self, session_id: str | None = None) -> bool:
        """Check if in GUI task execution mode."""
        return self.state_manager.is_running_task(session_id=session_id) and STATE.gui_mode

    def _is_complex_task_mode(self, session_id: str | None = None) -> bool:
        """Check if running a complex task."""
        return self.state_manager.is_running_task(session_id=session_id) and not self.task_manager.is_simple_task()

    def _is_simple_task_mode(self, session_id: str | None = None) -> bool:
        """Check if running a simple task."""
        return self.state_manager.is_running_task(session_id=session_id) and self.task_manager.is_simple_task()

    # ----- Workflow Handlers -----

    async def _handle_memory_workflow(self, trigger: Trigger) -> bool:
        """
        Handle memory processing workflow.

        Args:
            trigger: The memory processing trigger.

        Returns:
            True if a task was created and processing should continue,
            False if no task was created.
        """
        return await self._handle_memory_processing_trigger()

    async def _handle_conversation_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle conversation mode - no active task.
        Routes user queries to appropriate actions (send_message, task_start, etc.)
        Uses prefix caching only (no session caching for conversation mode).
        """
        logger.debug(f"[WORKFLOW: CONVERSATION] Query: {trigger_data.query}")

        # Use _select_action to maintain proper call chain
        action_decision, reasoning = await self._select_action(trigger_data)

        action, action_params, parent_id = await self._retrieve_and_prepare_action(
            action_decision, trigger_data.parent_id
        )

        action_output = await self._execute_action(
            action, action_params, trigger_data, reasoning, parent_id, session_id
        )

        new_session_id = action_output.get("task_id") or session_id
        await self._finalize_action_execution(new_session_id, action_output, session_id)

    async def _handle_simple_task_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle simple task mode - streamlined execution without todos.
        Quick tasks that auto-complete after delivering results.
        Uses session caching for efficient multi-turn execution.
        """
        logger.debug(f"[WORKFLOW: SIMPLE TASK] Query: {trigger_data.query}")

        # Use _select_action to maintain proper call chain with session caching
        action_decision, reasoning = await self._select_action(trigger_data)

        action, action_params, parent_id = await self._retrieve_and_prepare_action(
            action_decision, trigger_data.parent_id
        )

        action_output = await self._execute_action(
            action, action_params, trigger_data, reasoning, parent_id, session_id
        )

        new_session_id = action_output.get("task_id") or session_id
        await self._finalize_action_execution(new_session_id, action_output, session_id)

    async def _handle_complex_task_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle complex task mode - full todo workflow with planning.
        Multi-step tasks with todo management and user verification.
        Uses session caching for efficient multi-turn execution.
        """
        logger.debug(f"[WORKFLOW: COMPLEX TASK] Query: {trigger_data.query}")

        # Use _select_action to maintain proper call chain with session caching
        action_decision, reasoning = await self._select_action(trigger_data)

        action, action_params, parent_id = await self._retrieve_and_prepare_action(
            action_decision, trigger_data.parent_id
        )

        action_output = await self._execute_action(
            action, action_params, trigger_data, reasoning, parent_id, session_id
        )

        new_session_id = action_output.get("task_id") or session_id
        await self._finalize_action_execution(new_session_id, action_output, session_id)

    async def _handle_gui_task_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle GUI task mode - visual interaction workflow.
        Tasks requiring screen interaction via mouse/keyboard.
        """
        logger.debug("[WORKFLOW: GUI TASK] Entered GUI mode.")

        gui_response = await self._handle_gui_task_execution(trigger_data, session_id)

        await self._finalize_action_execution(
            gui_response.get("new_session_id"), gui_response.get("action_output"), session_id
        )

    # ----- GUI Task Helpers -----

    async def _handle_gui_task_execution(
        self, trigger_data: TriggerData, session_id: str
    ) -> dict:
        """
        Handle GUI mode task execution.

        Returns:
            Dictionary with action_output and new_session_id.
            Note: GUI events are now logged to main event stream directly.
        """
        current_todo = self.state_manager.get_current_todo()

        logger.debug("[GUI MODE] Entered GUI mode.")

        gui_response = await GUIHandler.gui_module.perform_gui_task_step(
            step=current_todo,
            session_id=session_id,
            next_action_description=trigger_data.query,
            parent_action_id=trigger_data.parent_id,
        )

        if gui_response.get("status") != "ok":
            raise ValueError(gui_response.get("message", "GUI task step failed"))

        action_output = gui_response.get("action_output", {})
        new_session_id = action_output.get("task_id") or session_id

        return {
            "action_output": action_output,
            "new_session_id": new_session_id,
        }

    # ----- Action Selection -----

    @profile("agent_select_action", OperationCategory.AGENT_LOOP)
    async def _select_action(self, trigger_data: TriggerData) -> tuple[dict, str]:
        """
        Select an action based on current task state.

        Routes to appropriate action selection method:
        - Complex task: _select_action_in_task (with session caching)
        - Simple task: _select_action_in_simple_task (with session caching)
        - Conversation: action_router.select_action (prefix caching only)

        Returns:
            Tuple of (action_decision, reasoning) where reasoning is empty string
            for non-task contexts.
        """
        # CRITICAL: Use session_id to check THIS specific session's task state
        # Without session_id, checks global state which could be wrong in concurrent tasks
        is_running_task = self.state_manager.is_running_task(session_id=trigger_data.session_id)

        if is_running_task:
            # Check task mode - simple tasks use streamlined action selection
            if self.task_manager.is_simple_task():
                return await self._select_action_in_simple_task(trigger_data.query, trigger_data.session_id)
            else:
                return await self._select_action_in_task(trigger_data.query, trigger_data.session_id)
        else:
            logger.debug(f"[AGENT QUERY] {trigger_data.query}")
            action_decision = await self.action_router.select_action(query=trigger_data.query)
            if not action_decision:
                raise ValueError("Action router returned no decision.")
            return action_decision, ""

    @profile("agent_select_action_in_task", OperationCategory.AGENT_LOOP)
    async def _select_action_in_task(self, query: str, session_id: str | None = None) -> tuple[dict, str]:
        """
        Select action when running within a task context.

        Reasoning is now integrated into the action selection prompt,
        so this method directly calls the action router without a separate
        reasoning step.

        Args:
            query: The query/instruction for action selection.
            session_id: Session ID for session-specific state lookup.

        Returns:
            Tuple of (action_decision, reasoning)
        """
        # Single LLM call - reasoning is integrated into action selection
        action_decision = await self.action_router.select_action_in_task(
            query=query,
            GUI_mode=STATE.gui_mode,
            session_id=session_id,
        )

        if not action_decision:
            raise ValueError("Action router returned no decision.")

        # Extract reasoning from the action decision (now included in response)
        reasoning = action_decision.get("reasoning", "")
        logger.debug(f"[AGENT REASONING] {reasoning}")

        # Log reasoning to event stream (pass task_id for multi-task isolation)
        if self.event_stream_manager and reasoning:
            self.event_stream_manager.log(
                "agent reasoning",
                reasoning,
                severity="DEBUG",
                display_message=None,
                task_id=session_id,
            )
            self.state_manager.bump_event_stream()

        return action_decision, reasoning

    @profile("agent_select_action_in_simple_task", OperationCategory.AGENT_LOOP)
    async def _select_action_in_simple_task(self, query: str, session_id: str | None = None) -> tuple[dict, str]:
        """
        Select action for simple task mode - lighter weight than complex task.

        Reasoning is now integrated into the action selection prompt.
        Simple tasks use streamlined prompts and no todo workflow.
        They auto-end after delivering results.

        Args:
            query: The query/instruction for action selection.
            session_id: Session ID for session-specific state lookup.

        Returns:
            Tuple of (action_decision, reasoning)
        """
        # Single LLM call - reasoning is integrated into action selection
        action_decision = await self.action_router.select_action_in_simple_task(
            query=query,
            session_id=session_id,
        )

        if not action_decision:
            raise ValueError("Action router returned no decision.")

        # Extract reasoning from the action decision (now included in response)
        reasoning = action_decision.get("reasoning", "")
        logger.debug(f"[AGENT REASONING - SIMPLE TASK] {reasoning}")

        # Log reasoning to event stream (pass task_id for multi-task isolation)
        if self.event_stream_manager and reasoning:
            self.event_stream_manager.log(
                "agent reasoning",
                reasoning,
                severity="DEBUG",
                display_message=None,
                task_id=session_id,
            )
            self.state_manager.bump_event_stream()

        return action_decision, reasoning

    # ----- Action Execution -----

    async def _retrieve_and_prepare_action(
        self, action_decision: dict, initial_parent_id: str | None
    ) -> tuple[Action, dict, str | None]:
        """
        Retrieve action from library and determine parent action ID.
        
        Returns:
            Tuple of (action, action_params, parent_id)
        """
        action_name = action_decision.get("action_name")
        action_params = action_decision.get("parameters", {})
        
        if not action_name:
            raise ValueError("No valid action selected by the router.")

        action = self.action_library.retrieve_action(action_name)
        if action is None:
            raise ValueError(
                f"Action '{action_name}' not found in the library. "
                "Check DB connectivity or ensure the action is registered."
            )
        
        # Use provided parent ID or None
        parent_id = initial_parent_id

        return action, action_params, parent_id or None

    @profile("agent_execute_action", OperationCategory.AGENT_LOOP)
    async def _execute_action(
        self,
        action: Action,
        action_params: dict,
        trigger_data: TriggerData,
        reasoning: str,
        parent_id: str | None,
        session_id: str,
    ) -> dict:
        """Execute the selected action."""
        # CRITICAL: Use session_id to check THIS specific session's task state
        # Without session_id, checks global state which could be wrong in concurrent tasks
        is_running_task = self.state_manager.is_running_task(session_id=session_id)
        context = reasoning if reasoning else trigger_data.query
        
        logger.info(f"[ACTION] Ready to run {action}")
        
        return await self.action_manager.execute_action(
            action=action,
            context=context,
            event_stream=STATE.event_stream,
            parent_id=parent_id,
            session_id=session_id,
            is_running_task=is_running_task,
            input_data=action_params,
        )

    async def _finalize_action_execution(
        self, new_session_id: str, action_output: dict, session_id: str
    ) -> None:
        """Handle post-action cleanup and trigger scheduling."""
        self.state_manager.bump_event_stream()
        if not await self._check_agent_limits():
            return
        await self._create_new_trigger(new_session_id, action_output, STATE)

    # ----- Error Handling -----

    async def _handle_react_error(
        self,
        error: Exception,
        new_session_id: str | None,
        session_id: str,
        action_output: dict,
    ) -> None:
        """Handle errors during react execution."""
        tb = traceback.format_exc()
        logger.error(f"[REACT ERROR] {error}\n{tb}")

        session_to_use = new_session_id or session_id
        if not session_to_use or not self.event_stream_manager:
            return

        try:
            logger.debug("[REACT ERROR] Logging to event stream")
            self.event_stream_manager.log(
                "error",
                f"[REACT] {type(error).__name__}: {error}\n{tb}",
                display_message=None,
                task_id=session_to_use,
            )
            self.state_manager.bump_event_stream()
            await self._create_new_trigger(session_to_use, action_output, STATE)
        except Exception as e:
            logger.error(
                "[REACT ERROR] Failed to log to event stream or create trigger",
                exc_info=True,
            )

    # ----- Session Management -----

    def _cleanup_session(self) -> None:
        """Safely cleanup session state."""
        try:
            self.state_manager.clean_state()
        except Exception as e:
            logger.warning(f"[REACT] Failed to end session safely: {e}")

    # ----- Agent Limits -----

    async def _check_agent_limits(self) -> bool:
        agent_properties = STATE.get_agent_properties()
        action_count: int = agent_properties.get("action_count", 0)
        max_actions: int = agent_properties.get("max_actions_per_task", 0)
        token_count: int = agent_properties.get("token_count", 0)
        max_tokens: int = agent_properties.get("max_tokens_per_task", 0)
        current_task_id: str = agent_properties.get("current_task_id", "")

        # Check action limits
        if (action_count / max_actions) >= 1.0:
            # Log warning BEFORE cancelling task (stream is removed during cancel)
            if self.event_stream_manager:
                self.event_stream_manager.log(
                    "warning",
                    f"Action limit reached: 100% of the maximum actions ({max_actions} actions) has been used. Aborting task.",
                    display_message=f"Action limit reached: 100% of the maximum ({max_actions} actions) has been used. Aborting task.",
                    task_id=current_task_id,
                )
                self.state_manager.bump_event_stream()
            response = await self.task_manager.mark_task_cancel(reason=f"Task reached the maximum actions allowed limit: {max_actions}")
            task_cancelled: bool = response
            return not task_cancelled
        elif (action_count / max_actions) >= 0.8:
            if self.event_stream_manager:
                self.event_stream_manager.log(
                    "warning",
                    f"Action limit nearing: 80% of the maximum actions ({max_actions} actions) has been used. "
                    "Consider wrapping up the task or informing the user that the task may be too complex. "
                    "If necessary, mark the task as aborted to prevent premature termination.",
                    display_message=None,
                    task_id=current_task_id,
                )
                self.state_manager.bump_event_stream()
                return True

        # Check token limits
        if (token_count / max_tokens) >= 1.0:
            # Log warning BEFORE cancelling task (stream is removed during cancel)
            if self.event_stream_manager:
                self.event_stream_manager.log(
                    "warning",
                    f"Token limit reached: 100% of the maximum tokens ({max_tokens} tokens) has been used. Aborting task.",
                    display_message=f"Token limit reached: 100% of the maximum ({max_tokens} tokens) has been used. Aborting task.",
                    task_id=current_task_id,
                )
                self.state_manager.bump_event_stream()
            response = await self.task_manager.mark_task_cancel(reason=f"Task reached the maximum tokens allowed limit: {max_tokens}")
            task_cancelled: bool = response
            return not task_cancelled
        elif (token_count / max_tokens) >= 0.8:
            if self.event_stream_manager:
                self.event_stream_manager.log(
                    "warning",
                    f"Token limit nearing: 80% of the maximum tokens ({max_tokens} tokens) has been used. "
                    "Consider wrapping up the task or informing the user that the task may be too complex. "
                    "If necessary, mark the task as aborted to prevent premature termination.",
                    display_message=None,
                    task_id=current_task_id,
                )
                self.state_manager.bump_event_stream()
                return True

        # No limits close or reached
        return True

    # ----- Trigger Management -----

    async def _cleanup_session_triggers(self, session_id: str) -> None:
        """
        Remove all triggers associated with a session when its task ends.

        This callback is invoked by TaskManager when a task completes, errors,
        or is cancelled, ensuring that stale triggers no longer appear as
        "ACTIVE" in the routing prompt.

        Args:
            session_id: The task/session ID whose triggers should be removed.
        """
        try:
            await self.triggers.remove_sessions([session_id])
            logger.debug(f"[TRIGGER] Cleaned up triggers for session={session_id}")
        except Exception as e:
            logger.warning(f"[TRIGGER] Failed to cleanup triggers for session={session_id}: {e}")

    @profile("agent_create_new_trigger", OperationCategory.TRIGGER)
    async def _create_new_trigger(self, new_session_id, action_output, STATE):
        """
        Schedule a follow-up trigger when a task is ongoing.

        This helper inspects the current task state and enqueues a new trigger
        so the agent can continue multi-step executions. It is defensive by
        design so failures do not interrupt the main ``react`` loop.

        Args:
            new_session_id: Session identifier to continue.
            action_output: Result dictionary returned by the previous action
                execution; may contain timing metadata.
            state_session: The current :class:`StateSession` object, used to
                propagate session context and payload.
        """
        try:
            # CRITICAL: Pass session_id to is_running_task() to check THIS specific task
            # Without session_id, it checks global state which could be wrong in concurrent tasks
            if not self.state_manager.is_running_task(session_id=new_session_id):
                # Nothing to schedule if no task is running for THIS session
                logger.debug(f"[TRIGGER] No task running for session {new_session_id}, skipping trigger creation")
                return

            # Delay logic
            fire_at_delay = 0.0
            try:
                fire_at_delay = float(action_output.get("fire_at_delay", 0.0))
            except Exception:
                logger.error("[TRIGGER] Invalid fire_at_delay in action_output. Using 0.0", exc_info=True)

            fire_at = time.time() + fire_at_delay

            logger.debug(f"[TRIGGER] Creating new trigger for session: {new_session_id}")

            # Build and enqueue trigger safely
            try:
                await self.triggers.put(
                    Trigger(
                        fire_at=fire_at,
                        priority=5,
                        next_action_description="Perform the next best action for the task based on the todos and event stream",
                        session_id=new_session_id,
                        payload={
                            "gui_mode": STATE.gui_mode,
                        },
                    ),
                    skip_merge=True,  # Session is already explicitly set, no LLM merge check needed
                )
            except Exception as e:
                logger.error(f"[TRIGGER] Failed to enqueue trigger for session {new_session_id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[TRIGGER] Unexpected error in create_new_trigger: {e}", exc_info=True)

    # ----- Chat Handling -----

    def _format_sessions_for_routing(
        self,
        active_task_ids: List[str],
        triggers: Optional[List[Trigger]] = None
    ) -> str:
        """Format active sessions with rich context for routing prompt.

        Uses active task IDs from state_manager (not just triggers in queue) to ensure
        all running tasks are visible for routing decisions.

        Args:
            active_task_ids: List of task IDs from state_manager.main_state.active_task_ids
            triggers: Optional list of triggers (used to check waiting_for_reply status)

        Returns:
            Formatted string with session context for routing decisions.
        """
        if not active_task_ids:
            return "No existing sessions."

        # Build a lookup of triggers by session_id for waiting_for_reply status
        trigger_map = {}
        if triggers:
            for tr in triggers:
                if tr.session_id:
                    trigger_map[tr.session_id] = tr

        sections = []
        for i, task_id in enumerate(active_task_ids, 1):
            task = self.task_manager.tasks.get(task_id) if self.task_manager else None
            trigger = trigger_map.get(task_id)

            # Check waiting_for_reply from trigger OR from task state
            is_waiting = False
            if trigger and trigger.waiting_for_reply:
                is_waiting = True
            if task and hasattr(task, 'waiting_for_user_reply') and task.waiting_for_user_reply:
                is_waiting = True

            status = "WAITING FOR REPLY" if is_waiting else "ACTIVE"
            platform = trigger.payload.get("platform", "default") if trigger else "default"

            lines = [
                f"--- Session {i} ---",
                f"Session ID: {task_id}",
                f"Status: {status}",
            ]

            if task:
                lines.extend([
                    f"Task Name: \"{task.name}\"",
                    f"Original Request: \"{task.instruction}\"",
                    f"Mode: {task.mode}",
                    f"Created: {task.created_at}",
                ])

                # Todo progress
                if task.todos:
                    completed = sum(1 for t in task.todos if t.status == "completed")
                    in_progress_todo = next(
                        (t for t in task.todos if t.status == "in_progress"), None
                    )
                    lines.append(f"Progress: {completed}/{len(task.todos)} todos completed")
                    if in_progress_todo:
                        lines.append(f"Currently working on: \"{in_progress_todo.content}\"")

                # Get recent events from event stream for this task
                if self.event_stream_manager and task_id:
                    stream = self.event_stream_manager.get_stream_by_id(task_id)
                    if stream and stream.tail_events:
                        # Get last 10 events for better routing context
                        # (5 was insufficient - file creation events were missed)
                        recent_events = stream.tail_events[-10:]
                        lines.append("Recent Activity:")
                        for rec in recent_events:
                            # Only truncate very long event messages (500+ chars)
                            # Short truncation caused loss of important context like file paths
                            event_line = rec.compact_line()
                            if len(event_line) > 500:
                                event_line = event_line[:497] + "..."
                            lines.append(f"  - {event_line}")
            else:
                # Fallback to trigger description if no task found
                desc = trigger.next_action_description if trigger else "Unknown task"
                lines.append(f"Description: \"{desc}\"")

            lines.append(f"Platform: {platform}")

            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    async def _route_to_session(
        self,
        item_type: str,
        item_content: str,
        existing_sessions: str,
        source_platform: str = "default",
    ) -> Dict[str, Any]:
        """Route incoming item to appropriate session using unified prompt.

        Args:
            item_type: Type of incoming item ("message" or "trigger")
            item_content: The content of the message or trigger description
            existing_sessions: Formatted string of existing sessions
            source_platform: The platform the message came from (e.g., "cli", "gui")

        Returns:
            Dict with routing decision containing:
            - action: "route" | "new"
            - session_id: The session to route to (or "new")
            - reason: Explanation of the routing decision
        """
        prompt = ROUTE_TO_SESSION_PROMPT.format(
            item_type=item_type,
            item_content=item_content,
            source_platform=source_platform,
            conversation_id="N/A",  # CraftBot doesn't use conversation_id
            existing_sessions=existing_sessions,
        )

        logger.debug(f"[UNIFIED ROUTING PROMPT]:\n{prompt}")
        response = await self.llm.generate_response_async(
            system_prompt="You are a session routing system.",
            user_prompt=prompt,
        )
        logger.debug(f"[UNIFIED ROUTING RESPONSE]: {response}")

        try:
            result = json.loads(response)
            # Ensure action field exists for backward compatibility
            if "action" not in result:
                result["action"] = "route" if result.get("session_id", "new") != "new" else "new"
            return result
        except json.JSONDecodeError:
            logger.error("[ROUTING] Failed to parse routing response JSON")
            return {"action": "new", "session_id": "new", "reason": "Failed to parse routing response"}

    async def _handle_chat_message(self, payload: Dict):
        try:
            user_input: str = payload.get("text", "")
            if not user_input:
                logger.warning("Received empty message.")
                return

            chat_content = user_input
            logger.info(f"[CHAT RECEIVED] {chat_content}")
            gui_mode = payload.get("gui_mode")
            # Extract platform from payload (e.g., "cli", "gui", "tui")
            source_platform = "gui" if gui_mode else "cli"

            # Check active tasks — route message to matching session if possible
            # Use active_task_ids from state_manager (not just triggers in queue) to ensure
            # all running tasks are visible for routing, not just those waiting in queue
            active_task_ids = self.state_manager.get_main_state().active_task_ids
            triggers = await self.triggers.list_triggers()  # Still get triggers for waiting_for_reply status

            if active_task_ids:
                # Use unified routing prompt with rich task context
                existing_sessions = self._format_sessions_for_routing(active_task_ids, triggers)
                routing_result = await self._route_to_session(
                    item_type="message",
                    item_content=chat_content,
                    existing_sessions=existing_sessions,
                    source_platform=source_platform,
                )

                action = routing_result.get("action", "new")

                if action == "route":
                    matched_session_id = routing_result.get("session_id", "new")
                    if matched_session_id != "new":
                        # Fire the matched trigger so it gets priority,
                        # and attach the new user message so react() sees it.
                        if not await self.triggers.fire(
                            matched_session_id, message=chat_content
                        ):
                            logger.warning(
                                f"[CHAT] Trigger for session_id {matched_session_id} not found, creating new."
                            )
                        else:
                            logger.info(
                                f"[CHAT] Routed message to existing session {matched_session_id} "
                                f"(reason: {routing_result.get('reason', 'N/A')})"
                            )
                            return

            # No existing triggers matched or action == "new" — create a fresh session
            await self.state_manager.start_session(gui_mode)
            self.state_manager.record_user_message(chat_content)

            # skip_merge=True because we already did routing above
            await self.triggers.put(
                Trigger(
                    fire_at=time.time(),
                    priority=1,
                    next_action_description=(
                        "Please perform action that best suit this user chat "
                        f"you just received: {chat_content}"
                    ),
                    session_id=str(uuid.uuid4()),  # Generate unique session ID
                    payload={
                        "gui_mode": gui_mode,
                        "platform": source_platform,
                    },
                ),
                skip_merge=True,
            )

        except Exception as e:
            logger.error(f"Error handling incoming message: {e}", exc_info=True)

    # =====================================
    # Hooks
    # =====================================

    def _load_extra_system_prompt(self) -> str:
        """
        Sub-classes may override to return a *role-specific* system-prompt
        fragment that is **prepended** to the standard one.
        """
        return ""
    
    def _generate_role_info_prompt(self) -> str:
        """
        Subclasses override this to return role-specific system instructions
        (responsibilities, behaviour constraints, expected domain tasks, etc).
        """
        return "You are a general computer-use AI agent that can switch between CLI/GUI mode."

    def _build_db_interface(self, *, data_dir: str, chroma_path: str):
        """A tiny wrapper so a subclass can point to another DB/collection."""
        return DatabaseInterface(
            data_dir = data_dir, chroma_path=chroma_path
        )

    # =====================================
    # State Management
    # =====================================

    async def reset_agent_state(self) -> str:
        """
        Reset runtime state so the agent behaves like a fresh instance.

        Clears triggers, resets task and state managers, and purges event
        streams. Useful for debugging or user-initiated resets.

        Returns:
            Confirmation message summarizing the reset.
        """

        await self.triggers.clear()
        self.task_manager.reset()
        self.state_manager.reset()
        self.event_stream_manager.clear_all()

        return "Agent state reset. Starting fresh."

    async def trigger_soft_onboarding(self, reset: bool = False) -> Optional[str]:
        """
        Trigger soft onboarding interview task.

        This method centralizes soft onboarding logic so interfaces don't need
        to contain agent logic.

        Args:
            reset: If True, reset soft onboarding state first (for /onboarding command)

        Returns:
            Task ID if created, None if not needed or already in progress
        """
        from app.onboarding import onboarding_manager
        from app.onboarding.soft.task_creator import create_soft_onboarding_task
        from app.trigger import Trigger
        import time

        if reset:
            onboarding_manager.reset_soft_onboarding()

        # Create interview task
        task_id = create_soft_onboarding_task(self.task_manager)

        # Fire trigger to start the task
        trigger = Trigger(
            fire_at=time.time(),
            priority=1,
            next_action_description="Begin user profile interview",
            session_id=task_id,
            payload={"onboarding": True},
        )
        await self.triggers.put(trigger)

        logger.info(f"[ONBOARDING] Triggered soft onboarding task: {task_id}")
        return task_id

    async def _handle_onboarding_command(self) -> str:
        """
        Handle the /onboarding command to re-run soft onboarding.

        Returns:
            Message indicating the interview is starting.
        """
        await self.trigger_soft_onboarding(reset=True)
        return "Starting user profile interview. I'll ask you some questions to personalize your experience."

    def _parse_reasoning_response(self, response: str) -> ReasoningResult:
        """
        Parse and validate the structured JSON response from the reasoning LLM call.
        """
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {response}") from e

        if not isinstance(parsed, dict):
            raise ValueError(f"LLM response is not a JSON object: {parsed}")

        reasoning = parsed.get("reasoning")
        action_query = parsed.get("action_query")

        if not isinstance(reasoning, str) or not isinstance(action_query, str):
            raise ValueError(f"Invalid reasoning schema: {parsed}")

        return ReasoningResult(
            reasoning=reasoning,
            action_query=action_query,
        )

    # =====================================
    # Initialization
    # =====================================

    def reinitialize_llm(self, provider: str | None = None) -> bool:
        """Reinitialize LLM and VLM interfaces with updated configuration.

        Call this after updating environment variables with new API keys.

        Args:
            provider: Optional provider to switch to. If None, uses current provider.

        Returns:
            True if both LLM and VLM were initialized successfully.
        """
        llm_ok = self.llm.reinitialize(provider)
        vlm_ok = self.vlm.reinitialize(provider)

        if llm_ok and vlm_ok:
            logger.info(f"[AGENT] LLM and VLM reinitialized with provider: {self.llm.provider}")
            # Update GUI module provider if needed (only if GUI mode is enabled)
            gui_globally_enabled = os.getenv("GUI_MODE_ENABLED", "True") == "True"
            if gui_globally_enabled and hasattr(self, 'action_library') and hasattr(GUIHandler, 'gui_module'):
                GUIHandler.gui_module = GUIModule(
                    provider=self.llm.provider,
                    action_library=self.action_library,
                    action_router=self.action_router,
                    context_engine=self.context_engine,
                    action_manager=self.action_manager,
                    event_stream_manager=self.event_stream_manager,
                    tui_footage_callback=self._tui_footage_callback,
                )
        return llm_ok and vlm_ok

    @property
    def is_llm_initialized(self) -> bool:
        """Check if the LLM interface is properly initialized."""
        return self.llm.is_initialized

    # =====================================
    # MCP Integration
    # =====================================

    async def _initialize_mcp(self) -> None:
        """
        Initialize MCP (Model Context Protocol) client and register tools as actions.

        This method:
        1. Loads MCP configuration from app/config/mcp_config.json
        2. Connects to enabled MCP servers
        3. Discovers tools from each connected server
        4. Registers tools as actions in the ActionRegistry

        MCP tools become available as action sets (e.g., mcp_filesystem) that
        can be selected during task creation.
        """
        try:
            from app.mcp import mcp_client
            from app.config import PROJECT_ROOT

            config_path = PROJECT_ROOT / "app" / "config" / "mcp_config.json"

            if not config_path.exists():
                logger.info(f"[MCP] No MCP config found at {config_path}, skipping MCP initialization")
                return

            logger.info(f"[MCP] Loading config from {config_path}")

            # Initialize MCP client (loads config and connects to servers)
            await mcp_client.initialize(config_path)

            # Log connection status before registering
            status = mcp_client.get_status()
            connected_count = sum(1 for s in status.get("servers", {}).values() if s.get("connected"))
            total_servers = len(status.get("servers", {}))
            logger.info(f"[MCP] Connected to {connected_count}/{total_servers} servers")

            for server_name, server_info in status.get("servers", {}).items():
                if server_info.get("connected"):
                    logger.info(
                        f"[MCP] Server '{server_name}': {server_info['tool_count']} tools available"
                    )

            # Register MCP tools as actions
            tool_count = mcp_client.register_tools_as_actions()

            if tool_count > 0:
                logger.info(
                    f"[MCP] Successfully registered {tool_count} MCP tools as actions"
                )
            else:
                # Provide more detailed diagnostics
                if not mcp_client.servers:
                    logger.warning("[MCP] No MCP servers connected - check if Node.js/npx is installed")
                else:
                    for name, server in mcp_client.servers.items():
                        if not server.is_connected:
                            logger.warning(f"[MCP] Server '{name}' failed to connect")
                        elif not server.tools:
                            logger.warning(f"[MCP] Server '{name}' connected but has no tools")

        except ImportError as e:
            logger.warning(f"[MCP] MCP module not available: {e}")
        except Exception as e:
            import traceback
            logger.warning(f"[MCP] Failed to initialize MCP: {e}")
            logger.debug(f"[MCP] Traceback: {traceback.format_exc()}")

    async def _shutdown_memory_scheduler(self) -> None:
        """Cancel the background memory processing scheduler."""
        self.is_running = False  # Signal scheduler loop to exit
        if self._memory_scheduler_task and not self._memory_scheduler_task.done():
            self._memory_scheduler_task.cancel()
            try:
                await self._memory_scheduler_task
            except asyncio.CancelledError:
                pass
            logger.debug("[MEMORY] Memory processing scheduler shut down")

    async def _shutdown_mcp(self) -> None:
        """Gracefully disconnect from all MCP servers."""
        try:
            from app.mcp import mcp_client
            await mcp_client.disconnect_all()
            logger.info("[MCP] Disconnected from all MCP servers")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[MCP] Error during MCP shutdown: {e}")

    # =====================================
    # Skills Integration
    # =====================================

    async def _initialize_skills(self) -> None:
        """
        Initialize the skills system and discover available skills.

        This method:
        1. Loads skills configuration from app/config/skills_config.json
        2. Discovers skills from global (~/.whitecollar/skills/) and project directories
        3. Makes skills available for automatic selection during task creation

        Skills provide specialized instructions that are injected into context
        when selected for a task.
        """
        try:
            from app.skill import skill_manager
            from app.config import PROJECT_ROOT

            config_path = PROJECT_ROOT / "app" / "config" / "skills_config.json"

            logger.info(f"[SKILLS] Loading config from {config_path}")

            # Initialize skill manager (loads config and discovers skills)
            await skill_manager.initialize(config_path)

            # Log discovered skills
            status = skill_manager.get_status()
            total_skills = status.get("total_skills", 0)
            enabled_skills = status.get("enabled_skills", 0)

            if total_skills > 0:
                logger.info(f"[SKILLS] Discovered {total_skills} skills ({enabled_skills} enabled)")
                for skill_name, skill_info in status.get("skills", {}).items():
                    if skill_info.get("enabled"):
                        logger.debug(f"[SKILLS] - {skill_name}: {skill_info.get('description', 'No description')}")
            else:
                logger.info("[SKILLS] No skills discovered. Create skills in ~/.whitecollar/skills/ or .whitecollar/skills/")

        except ImportError as e:
            logger.warning(f"[SKILLS] Skill module not available: {e}")
        except Exception as e:
            import traceback
            logger.warning(f"[SKILLS] Failed to initialize skills: {e}")
            logger.debug(f"[SKILLS] Traceback: {traceback.format_exc()}")

    # =====================================
    # External Libraries
    # =====================================

    async def _initialize_external_libraries(self) -> None:
        """Initialize all external app libraries."""
        try:
            from agent_core.external_libraries.notion.external_app_library import NotionAppLibrary
            from agent_core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
            from agent_core.external_libraries.slack.external_app_library import SlackAppLibrary
            from agent_core.external_libraries.telegram.external_app_library import TelegramAppLibrary
            from agent_core.external_libraries.linkedin.external_app_library import LinkedInAppLibrary
            from agent_core.external_libraries.zoom.external_app_library import ZoomAppLibrary
            from agent_core.external_libraries.discord.external_app_library import DiscordAppLibrary
            from agent_core.external_libraries.recall.external_app_library import RecallAppLibrary
            from agent_core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary

            NotionAppLibrary.initialize()
            WhatsAppAppLibrary.initialize()
            SlackAppLibrary.initialize()
            TelegramAppLibrary.initialize()
            LinkedInAppLibrary.initialize()
            ZoomAppLibrary.initialize()
            DiscordAppLibrary.initialize()
            RecallAppLibrary.initialize()
            GoogleWorkspaceAppLibrary.initialize()
            
            logger.info("[EXT LIBS] External libraries initialized")
        except Exception as e:
            logger.warning(f"[EXT LIBS] Failed to initialize external libraries: {e}")

    # =====================================
    # Lifecycle
    # =====================================

    async def run(
        self,
        *,
        provider: str | None = None,
        api_key: str = "",
        interface_mode: str = "tui",
    ) -> None:
        """
        Launch the interactive loop for the agent.

        Args:
            provider: Optional provider override passed to the interface before
                chat starts; defaults to the provider configured during
                initialization.
            api_key: Optional API key presented in the interface for convenience.
            interface_mode: "tui" for Textual interface, "cli" for command line.
        """
        # Initialize MCP client and register tools
        await self._initialize_mcp()

        # Initialize skills system
        await self._initialize_skills()

        # Initialize external app libraries
        await self._initialize_external_libraries()

        # Process unprocessed events into memory at startup (if enabled)
        if PROCESS_MEMORY_AT_STARTUP:
            await self._process_memory_at_startup()

        # Schedule daily memory processing
        await self._schedule_daily_memory_processing()

        # Trigger soft onboarding if needed (BEFORE starting interface)
        # This ensures agent handles onboarding logic, not the interfaces
        from app.onboarding import onboarding_manager
        if onboarding_manager.needs_soft_onboarding:
            logger.info("[ONBOARDING] Soft onboarding needed, triggering from agent")
            await self.trigger_soft_onboarding()

        try:
            # Select interface based on mode
            if interface_mode == "cli":
                from app.cli import CLIInterface
                interface = CLIInterface(
                    self,
                    default_provider=provider or self.llm.provider,
                    default_api_key=api_key,
                )
            else:
                interface = TUIInterface(
                    self,
                    default_provider=provider or self.llm.provider,
                    default_api_key=api_key,
                )

            await interface.start()
        finally:
            # Cancel memory processing scheduler
            await self._shutdown_memory_scheduler()
            # Gracefully shutdown MCP connections
            await self._shutdown_mcp()