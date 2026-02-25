# -*- coding: utf-8 -*-
"""Recall.ai credential dataclasses."""

from dataclasses import dataclass
from typing import ClassVar
from agent_core.external_libraries.credential_store import Credential


@dataclass
class RecallCredential(Credential):
    """
    Recall.ai API credentials.

    Recall.ai uses API keys for authentication, not OAuth.
    """
    user_id: str
    api_key: str = ""
    region: str = "us"  # "us" or "eu"

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id",)
