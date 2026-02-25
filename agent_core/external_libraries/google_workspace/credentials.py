# -*- coding: utf-8 -*-
"""Google Workspace credential dataclasses."""

from dataclasses import dataclass
from typing import ClassVar, Optional
from agent_core.external_libraries.credential_store import Credential


@dataclass
class GoogleWorkspaceCredential(Credential):
    """Google Workspace OAuth credential."""
    user_id: str
    email: str
    token: str
    refresh_token: str
    token_expiry: Optional[float] = None  # Unix timestamp when token expires
    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "email")
