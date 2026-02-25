# -*- coding: utf-8 -*-
"""External libraries - re-exports from agent_core."""

from agent_core.external_libraries import (
    ExternalAppLibrary,
    CredentialsStore,
    RemoteCredentialStore,
)

# Re-export integration modules
from agent_core.external_libraries import discord
from agent_core.external_libraries import google_workspace
from agent_core.external_libraries import slack
from agent_core.external_libraries import telegram
from agent_core.external_libraries import notion
from agent_core.external_libraries import linkedin
from agent_core.external_libraries import whatsapp
from agent_core.external_libraries import zoom
from agent_core.external_libraries import recall

__all__ = [
    "ExternalAppLibrary",
    "CredentialsStore",
    "RemoteCredentialStore",
    "discord",
    "google_workspace",
    "slack",
    "telegram",
    "notion",
    "linkedin",
    "whatsapp",
    "zoom",
    "recall",
]
