# -*- coding: utf-8 -*-
"""Zoom credential dataclasses."""

from dataclasses import dataclass
from typing import ClassVar, Optional
from agent_core.external_libraries.credential_store import Credential


@dataclass
class ZoomCredential(Credential):
    """
    Zoom OAuth 2.0 credentials.

    Supports Zoom user accounts with meeting management capabilities.
    """
    user_id: str
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: Optional[float] = None
    zoom_user_id: str = ""
    email: str = ""
    display_name: str = ""
    account_id: str = ""

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "zoom_user_id")
