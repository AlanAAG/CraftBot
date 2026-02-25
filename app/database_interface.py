# -*- coding: utf-8 -*-
"""
Database interface module - re-exports from agent_core.

All database implementations are now in agent_core.
"""

# Re-export from agent_core
from agent_core import DatabaseInterface

__all__ = ["DatabaseInterface"]
