# -*- coding: utf-8 -*-
"""Telegram credential dataclasses."""

from dataclasses import dataclass
from typing import ClassVar, Literal
from agent_core.external_libraries.credential_store import Credential


@dataclass
class TelegramCredential(Credential):
    """
    Telegram credential supporting both Bot API and MTProto (User Account) connections.

    For Bot API:
        - Set connection_type="bot_api"
        - Provide bot_id, bot_username, bot_token

    For MTProto (User Account):
        - Set connection_type="mtproto"
        - Provide phone_number, api_id, api_hash
        - session_string is populated after successful authentication
    """
    user_id: str
    connection_type: Literal["bot_api", "mtproto"] = "bot_api"

    # Bot API fields
    bot_id: str = ""
    bot_username: str = ""
    bot_token: str = ""

    # MTProto (User Account) fields
    phone_number: str = ""
    api_id: int = 0
    api_hash: str = ""
    session_string: str = ""
    account_name: str = ""
    telegram_user_id: int = 0

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "bot_id", "phone_number")
