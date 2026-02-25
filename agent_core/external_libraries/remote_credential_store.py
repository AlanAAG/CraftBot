# -*- coding: utf-8 -*-
"""
Remote credential store - fetches credentials from backend on-demand.

Replaces local JSON file storage with backend-managed credentials.
Maintains an in-memory cache with TTL for performance.
"""

import asyncio
import concurrent.futures
import time
import logging
from dataclasses import fields
from typing import Dict, List, TypeVar, Generic, Type, Optional, Tuple, Any

from agent_core.external_libraries.credential_store import Credential
from agent_core.core.config import get_credential_client

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=Credential)


class RemoteCredentialStore(Generic[T]):
    """
    Credential store that fetches credentials from backend on-demand.
    Maintains an in-memory cache with TTL for performance.

    This replaces the local CredentialsStore for backend-managed credentials.
    """

    # Map integration types to their service ID field names
    # Must match the actual field names in each credential dataclass
    SERVICE_ID_FIELDS = {
        "slack": "workspace_id",
        "google_workspace": "email",
        "notion": "workspace_id",
        "linkedin": "linkedin_id",
        "zoom": "zoom_user_id",
        "telegram_bot": "bot_id",
        "telegram_mtproto": "phone_number",
        "whatsapp": "phone_number_id",
        "whatsapp_web": "phone_number_id",
        "discord_bot": "bot_id",
        "discord_user": "discord_user_id",
        "recall": "api_key",
    }

    # Map backend field names -> dataclass field names where they differ
    FIELD_NAME_MAP = {
        "whatsapp_web": {"phone_number": "phone_number_id"},
    }

    def __init__(
        self,
        credential_cls: Type[T],
        integration_type: str,
        cache_ttl_seconds: int = 300,  # 5 minute default cache
    ):
        """
        Initialize the remote credential store.

        Args:
            credential_cls: The dataclass type for credentials (e.g., SlackCredential)
            integration_type: The integration type string (e.g., "slack")
            cache_ttl_seconds: How long to cache credentials (default 5 minutes)
        """
        self.credential_cls = credential_cls
        self.integration_type = integration_type
        self.cache_ttl = cache_ttl_seconds

        # In-memory cache: (user_id, service_id) -> (credential, timestamp)
        self._cache: Dict[Tuple[str, Optional[str]], Tuple[Optional[T], float]] = {}

    def _get_service_id_field(self) -> str:
        """Get the service-specific ID field name for this integration."""
        return self.SERVICE_ID_FIELDS.get(self.integration_type, "service_account_id")

    def _create_credential_from_data(self, data: Dict[str, Any]) -> T:
        """
        Create a credential instance from backend data.

        Handles field name mapping and missing optional fields.
        """
        # Apply field name mappings for this integration type
        name_map = self.FIELD_NAME_MAP.get(self.integration_type, {})
        mapped_data = {}
        for key, value in data.items():
            mapped_key = name_map.get(key, key)
            mapped_data[mapped_key] = value

        # Get the fields expected by the credential class
        expected_fields = {f.name for f in fields(self.credential_cls)}

        # Filter data to only include expected fields
        filtered_data = {}
        for key, value in mapped_data.items():
            if key in expected_fields:
                filtered_data[key] = value

        # Create and return the credential
        return self.credential_cls(**filtered_data)

    def _check_cache(self, user_id: str, **filters) -> Tuple[bool, List[T]]:
        """Check cache and return (hit, results)."""
        service_id_field = self._get_service_id_field()
        service_account_id = filters.get(service_id_field)
        cache_key = (user_id, service_account_id)

        if cache_key in self._cache:
            credential, timestamp = self._cache[cache_key]
            age = time.time() - timestamp
            if age < self.cache_ttl:
                logger.debug(
                    f"[RemoteCredentialStore] Cache HIT for {self.integration_type} "
                    f"(age={age:.0f}s)"
                )
                return True, ([credential] if credential else [])
            else:
                logger.debug(
                    f"[RemoteCredentialStore] Cache EXPIRED for {self.integration_type} "
                    f"(age={age:.0f}s, ttl={self.cache_ttl}s)"
                )
        return False, []

    async def _fetch_from_backend(self, user_id: str, service_account_id: Optional[str] = None) -> List[T]:
        """Async fetch from backend and update cache."""
        client = get_credential_client()
        if not client:
            logger.warning(
                f"[RemoteCredentialStore] Credential client not initialized for {self.integration_type}"
            )
            return []

        cache_key = (user_id, service_account_id)
        logger.info(
            f"[RemoteCredentialStore] Fetching {self.integration_type} credential"
            + (f" (service_account_id={service_account_id})" if service_account_id else "")
        )
        try:
            data = await client.request_credential(
                integration_type=self.integration_type,
                user_id=user_id,
                service_account_id=service_account_id,
            )

            if data:
                credential = self._create_credential_from_data(data)
                self._cache[cache_key] = (credential, time.time())
                logger.info(
                    f"[RemoteCredentialStore] Cached {self.integration_type} credential"
                )
                return [credential]
            else:
                self._cache[cache_key] = (None, time.time())
                logger.warning(
                    f"[RemoteCredentialStore] No {self.integration_type} credential found"
                )
                return []

        except Exception as e:
            logger.error(
                f"[RemoteCredentialStore] Failed to fetch {self.integration_type} credential: {e}",
                exc_info=True,
            )
            return []

    def get(self, user_id: str, **filters) -> List[T]:
        """
        Fetch credentials for a user (synchronous).

        Checks cache first. On cache miss, fetches from backend via a thread
        so this works whether called from sync or async code.
        This matches the CredentialsStore.get() interface so LLM-generated
        action code works seamlessly.

        Args:
            user_id: The user ID to fetch credentials for
            **filters: Additional filters (e.g., workspace_id="T123")

        Returns:
            List of matching credentials (usually 0 or 1)
        """
        hit, results = self._check_cache(user_id, **filters)
        if hit:
            return results

        # Cache miss - fetch from backend
        service_id_field = self._get_service_id_field()
        service_account_id = filters.get(service_id_field)

        try:
            # Run async fetch in a thread to avoid blocking the event loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self._fetch_from_backend(user_id, service_account_id),
                )
                return future.result(timeout=15)
        except Exception as e:
            logger.error(
                f"[RemoteCredentialStore] Sync fetch failed for {self.integration_type}: {e}"
            )
            return []

    async def get_async(self, user_id: str, **filters) -> List[T]:
        """
        Fetch credentials for a user (async).

        Same as get() but can be awaited directly without thread overhead.

        Args:
            user_id: The user ID to fetch credentials for
            **filters: Additional filters (e.g., workspace_id="T123")

        Returns:
            List of matching credentials (usually 0 or 1)
        """
        hit, results = self._check_cache(user_id, **filters)
        if hit:
            return results

        service_id_field = self._get_service_id_field()
        service_account_id = filters.get(service_id_field)
        return await self._fetch_from_backend(user_id, service_account_id)

    def get_sync(self, user_id: str, **filters) -> List[T]:
        """
        Cache-only synchronous check (no network calls).

        Use this for lightweight checks where you don't want to block.
        """
        hit, results = self._check_cache(user_id, **filters)
        return results if hit else []

    def invalidate_cache(
        self,
        user_id: str,
        service_account_id: Optional[str] = None
    ) -> None:
        """
        Clear cached credentials for a user.

        Args:
            user_id: The user whose cache to clear
            service_account_id: Optional specific service account to clear
        """
        if service_account_id:
            # Clear specific cache entry
            cache_key = (user_id, service_account_id)
            self._cache.pop(cache_key, None)
        else:
            # Clear all cache entries for this user
            keys_to_remove = [k for k in self._cache.keys() if k[0] == user_id]
            for key in keys_to_remove:
                self._cache.pop(key, None)

    def clear_cache(self) -> None:
        """Clear all cached credentials."""
        self._cache.clear()

    # --- Deprecated methods (kept for backward compatibility) ---

    def add(self, credential: T) -> None:
        """
        DEPRECATED: Credentials are now managed by the backend.
        This method is kept for backward compatibility but only updates local cache.
        """
        logger.warning(
            f"[RemoteCredentialStore] add() is deprecated - credentials are backend-managed"
        )
        # Update local cache only
        service_id_field = self._get_service_id_field()
        service_account_id = getattr(credential, service_id_field, None)
        cache_key = (credential.user_id, service_account_id)
        self._cache[cache_key] = (credential, time.time())

    def remove(self, user_id: str, **filters) -> None:
        """
        DEPRECATED: Credentials are now managed by the backend.
        This method only clears local cache.
        """
        logger.info(
            f"[RemoteCredentialStore] remove() called - clearing local cache only"
        )
        service_id_field = self._get_service_id_field()
        service_account_id = filters.get(service_id_field)
        self.invalidate_cache(user_id, service_account_id)

    def load(self) -> None:
        """DEPRECATED: No-op for remote credential store."""
        pass

    def save(self) -> None:
        """DEPRECATED: No-op for remote credential store."""
        pass
