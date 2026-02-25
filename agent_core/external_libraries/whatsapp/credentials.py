# -*- coding: utf-8 -*-
"""WhatsApp credential dataclasses."""

from dataclasses import dataclass
from typing import ClassVar
from agent_core.external_libraries.credential_store import Credential


@dataclass
class WhatsAppCredential(Credential):
    """
    WhatsApp credential for WhatsApp Web connections via QR code (session-based).
    """
    user_id: str
    phone_number_id: str

    # WhatsApp Web fields
    session_id: str = ""
    session_data: str = ""
    jid: str = ""

    # Common fields
    display_phone_number: str = ""

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "phone_number_id")
