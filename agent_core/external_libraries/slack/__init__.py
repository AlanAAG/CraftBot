# -*- coding: utf-8 -*-
"""Slack integration library."""

from agent_core.external_libraries.slack.credentials import SlackCredential
from agent_core.external_libraries.slack.external_app_library import SlackAppLibrary

__all__ = [
    "SlackCredential",
    "SlackAppLibrary",
]
