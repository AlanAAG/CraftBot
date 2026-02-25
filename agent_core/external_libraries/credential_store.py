# -*- coding: utf-8 -*-
"""
Local credential store with JSON persistence.

Generic credential store that persists credentials to local JSON files.
Each store handles a single credential type.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, TypeVar, Generic, Type
import json
from pathlib import Path
from agent_core.core.config import get_workspace_root


@dataclass
class Credential:
    """Base credential class."""
    user_id: str
    UNIQUE_KEYS: tuple = ()

    def to_dict(self) -> Dict:
        """Convert credential to dictionary."""
        return asdict(self)


T = TypeVar('T', bound=Credential)


class CredentialsStore(Generic[T]):
    """
    Generic credential store with local JSON persistence.
    Each store handles a single credential type.
    """

    def __init__(self, credential_cls: Type[T], persistence_file: str):
        """
        Initialize the credential store.

        Args:
            credential_cls: The dataclass type for credentials
            persistence_file: Filename for JSON persistence (relative to .credentials/)
        """
        self.credential_cls = credential_cls
        self.credentials: Dict[str, List[T]] = {}
        self.persistence_path = Path(get_workspace_root()) / ".credentials" / persistence_file
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self):
        """Load credentials from disk."""
        if not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path, "r") as f:
                data = json.load(f)

            for user_id, cred_list in data.items():
                self.credentials[user_id] = [self.credential_cls(**item) for item in cred_list]
        except Exception as e:
            print(f"[CredentialsStore] Failed to load credentials: {e}")

    def save(self):
        """Save credentials to disk."""
        output = {
            user_id: [asdict(c) for c in creds]
            for user_id, creds in self.credentials.items()
        }

        try:
            with open(self.persistence_path, "w") as f:
                json.dump(output, f, indent=2)
        except Exception as e:
            print(f"[CredentialsStore] Failed to save credentials: {e}")

    def add(self, credential: T) -> None:
        """Add or update a credential."""
        creds = self.credentials.setdefault(credential.user_id, [])

        # Replace if unique keys match
        for i, existing in enumerate(creds):
            if all(getattr(existing, k, None) == getattr(credential, k, None)
                   for k in getattr(credential, "UNIQUE_KEYS", ())):
                creds[i] = credential
                self.save()
                return

        creds.append(credential)
        self.save()

    def get(self, user_id: str, **filters) -> List[T]:
        """
        Get credentials for a user.

        Args:
            user_id: The user ID to fetch credentials for
            **filters: Optional key=value pairs to filter results

        Returns:
            List of matching credentials
        """
        creds = self.credentials.get(user_id, [])
        for key, value in filters.items():
            creds = [c for c in creds if getattr(c, key, None) == value]
        return creds

    def remove(self, user_id: str, **filters) -> None:
        """
        Remove credentials for a user.

        Args:
            user_id: The user whose credentials to remove
            **filters: Optional key=value pairs to match credentials to remove
        """
        if user_id not in self.credentials:
            return

        creds = self.credentials[user_id]
        remaining = [c for c in creds if not all(getattr(c, k, None) == v for k, v in filters.items())]

        if remaining:
            self.credentials[user_id] = remaining
        else:
            self.credentials.pop(user_id)

        self.save()
