# -*- coding: utf-8 -*-
"""Notion credential dataclasses."""

from dataclasses import dataclass
from typing import ClassVar
from agent_core.external_libraries.credential_store import Credential


@dataclass
class NotionCredential(Credential):
    """Notion workspace OAuth credential."""
    user_id: str
    workspace_id: str
    workspace_name: str
    token: str
    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "workspace_id")
