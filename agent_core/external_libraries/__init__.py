# -*- coding: utf-8 -*-
"""
External library integrations.

Provides OAuth-based integrations with external services like
Discord, Google Workspace, Slack, Notion, etc.
"""

from agent_core.external_libraries.credential_store import Credential, CredentialsStore
from agent_core.external_libraries.remote_credential_store import RemoteCredentialStore
from agent_core.external_libraries.external_app_library import ExternalAppLibrary

# Credential types (import lazily to avoid circular imports)
from agent_core.external_libraries.discord.credentials import (
    DiscordBotCredential,
    DiscordUserCredential,
    DiscordSharedBotGuildCredential,
)
from agent_core.external_libraries.google_workspace.credentials import GoogleWorkspaceCredential
from agent_core.external_libraries.slack.credentials import SlackCredential
from agent_core.external_libraries.notion.credentials import NotionCredential
from agent_core.external_libraries.linkedin.credentials import LinkedInCredential
from agent_core.external_libraries.telegram.credentials import TelegramCredential
from agent_core.external_libraries.recall.credentials import RecallCredential
from agent_core.external_libraries.whatsapp.credentials import WhatsAppCredential
from agent_core.external_libraries.zoom.credentials import ZoomCredential

# App libraries
from agent_core.external_libraries.discord.external_app_library import DiscordAppLibrary
from agent_core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary
from agent_core.external_libraries.slack.external_app_library import SlackAppLibrary

__all__ = [
    # Base classes
    "Credential",
    "CredentialsStore",
    "RemoteCredentialStore",
    "ExternalAppLibrary",
    # Credential types
    "DiscordBotCredential",
    "DiscordUserCredential",
    "DiscordSharedBotGuildCredential",
    "GoogleWorkspaceCredential",
    "SlackCredential",
    "NotionCredential",
    "LinkedInCredential",
    "TelegramCredential",
    "RecallCredential",
    "WhatsAppCredential",
    "ZoomCredential",
    # App libraries
    "DiscordAppLibrary",
    "GoogleWorkspaceAppLibrary",
    "SlackAppLibrary",
]
