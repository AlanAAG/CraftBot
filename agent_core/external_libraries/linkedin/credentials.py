# -*- coding: utf-8 -*-
"""LinkedIn credential dataclasses."""

from dataclasses import dataclass
from typing import ClassVar, Optional
from agent_core.external_libraries.credential_store import Credential


@dataclass
class LinkedInCredential(Credential):
    """
    LinkedIn OAuth 2.0 credentials.

    Supports both personal profiles and company page access.
    LinkedIn uses URNs for identification (urn:li:person:xxx, urn:li:organization:xxx).
    """
    user_id: str
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: Optional[float] = None
    linkedin_id: str = ""
    name: str = ""
    email: str = ""
    profile_picture_url: str = ""
    organization_id: str = ""
    organization_name: str = ""

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "linkedin_id")
