# -*- coding: utf-8 -*-
"""Slack App Library"""

from typing import Optional, Dict, Any, List, Union

from agent_core.external_libraries.external_app_library import ExternalAppLibrary
from agent_core.external_libraries.credential_store import CredentialsStore
from agent_core.external_libraries.remote_credential_store import RemoteCredentialStore
from agent_core.external_libraries.slack.credentials import SlackCredential
from agent_core.external_libraries.slack.helpers.slack_helpers import (
    send_message,
    list_channels,
    list_users,
    get_channel_history,
    get_user_info,
    create_channel,
    invite_to_channel,
    upload_file,
    get_channel_info,
    search_messages,
    open_dm,
)
from agent_core.core.config import get_config


class SlackAppLibrary(ExternalAppLibrary):
    """Slack integration library."""
    _name = "Slack"
    _version = "2.0.0"
    _credential_store: Optional[Union[CredentialsStore, RemoteCredentialStore]] = None
    _initialized: bool = False
    _use_remote: bool = False

    @classmethod
    def initialize(cls):
        """Initialize the Slack library with its credential store."""
        if cls._initialized:
            return

        cls._use_remote = get_config("USE_REMOTE_CREDENTIALS", False)

        if cls._use_remote:
            cls._credential_store = RemoteCredentialStore(
                credential_cls=SlackCredential,
                integration_type="slack",
            )
        else:
            cls._credential_store = CredentialsStore(
                credential_cls=SlackCredential,
                persistence_file="slack_credentials.json",
            )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> Union[CredentialsStore, RemoteCredentialStore]:
        if cls._credential_store is None:
            raise RuntimeError("SlackAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, workspace_id: Optional[str] = None) -> bool:
        """Returns True if a Slack credential exists for the user."""
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            if workspace_id:
                credentials = cred_store.get_sync(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get_sync(user_id=user_id)
        else:
            if workspace_id:
                credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    async def validate_connection_async(cls, user_id: str, workspace_id: Optional[str] = None) -> bool:
        """Async version of validate_connection."""
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            if workspace_id:
                credentials = await cred_store.get_async(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = await cred_store.get_async(user_id=user_id)
        else:
            if workspace_id:
                credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    def get_credentials(
        cls,
        user_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[SlackCredential]:
        """Retrieve the Slack credential for the user."""
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            if workspace_id:
                credentials = cred_store.get_sync(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get_sync(user_id=user_id)
        else:
            if workspace_id:
                credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    @classmethod
    async def get_credentials_async(
        cls,
        user_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[SlackCredential]:
        """Async version of get_credentials."""
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            if workspace_id:
                credentials = await cred_store.get_async(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = await cred_store.get_async(user_id=user_id)
        else:
            if workspace_id:
                credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    @classmethod
    def send_message(
        cls,
        user_id: str,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a message to a Slack channel or DM."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = send_message(
                bot_token=credential.bot_token,
                channel=channel,
                text=text,
                thread_ts=thread_ts,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "message": result}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def list_channels(
        cls,
        user_id: str,
        types: str = "public_channel,private_channel",
        limit: int = 100,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List channels in the Slack workspace."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = list_channels(
                bot_token=credential.bot_token,
                types=types,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channels": result.get("channels", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def list_users(
        cls,
        user_id: str,
        limit: int = 100,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List users in the Slack workspace."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = list_users(
                bot_token=credential.bot_token,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "users": result.get("members", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_user_info(
        cls,
        user_id: str,
        slack_user_id: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get information about a Slack user."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = get_user_info(
                bot_token=credential.bot_token,
                user_id=slack_user_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "user": result.get("user")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_channel_history(
        cls,
        user_id: str,
        channel: str,
        limit: int = 100,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get message history from a channel."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = get_channel_history(
                bot_token=credential.bot_token,
                channel=channel,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "messages": result.get("messages", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_channel_info(
        cls,
        user_id: str,
        channel: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get information about a channel."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = get_channel_info(
                bot_token=credential.bot_token,
                channel=channel,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def create_channel(
        cls,
        user_id: str,
        name: str,
        is_private: bool = False,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new Slack channel."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = create_channel(
                bot_token=credential.bot_token,
                name=name,
                is_private=is_private,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def invite_to_channel(
        cls,
        user_id: str,
        channel: str,
        users: List[str],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invite users to a channel."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = invite_to_channel(
                bot_token=credential.bot_token,
                channel=channel,
                users=users,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def upload_file(
        cls,
        user_id: str,
        channels: List[str],
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a file to Slack."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = upload_file(
                bot_token=credential.bot_token,
                channels=channels,
                content=content,
                file_path=file_path,
                filename=filename,
                title=title,
                initial_comment=initial_comment,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "file": result.get("file")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def search_messages(
        cls,
        user_id: str,
        query: str,
        count: int = 20,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search for messages in the workspace."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = search_messages(
                bot_token=credential.bot_token,
                query=query,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "messages": result.get("messages", {})}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def open_dm(
        cls,
        user_id: str,
        users: List[str],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open a DM or group DM with users."""
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = open_dm(
                bot_token=credential.bot_token,
                users=users,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}
