# -*- coding: utf-8 -*-
"""
Temporary local HTTP server for OAuth callbacks.

This module provides a simple OAuth callback server that can be used
to capture authorization codes from OAuth flows.

Usage:
    from agent_core.core.credentials.oauth_server import run_oauth_flow

    # Run OAuth flow (opens browser, waits for callback)
    code, error = run_oauth_flow("https://provider.com/oauth/authorize?...")

    if error:
        print(f"OAuth failed: {error}")
    else:
        # Use code for token exchange
        print(f"Got authorization code: {code}")
"""

import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback requests."""

    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        """Handle GET request from OAuth callback."""
        params = parse_qs(urlparse(self.path).query)
        _OAuthCallbackHandler.code = params.get("code", [None])[0]
        _OAuthCallbackHandler.state = params.get("state", [None])[0]
        _OAuthCallbackHandler.error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if _OAuthCallbackHandler.code:
            self.wfile.write(
                b"<h2>Authorization successful!</h2><p>You can close this tab.</p>"
            )
        else:
            self.wfile.write(
                f"<h2>Failed</h2><p>{_OAuthCallbackHandler.error}</p>".encode()
            )

    def log_message(self, format, *args):
        """Suppress HTTP server logging."""
        pass


def run_oauth_flow(
    auth_url: str, port: int = 8765, timeout: int = 120
) -> Tuple[Optional[str], Optional[str]]:
    """
    Open browser for OAuth, wait for callback.

    This function:
    1. Starts a temporary HTTP server on localhost
    2. Opens the authorization URL in the user's browser
    3. Waits for the OAuth provider to redirect back with a code
    4. Returns the authorization code (or error)

    Args:
        auth_url: The full OAuth authorization URL to open
        port: Local port for callback server (default: 8765)
        timeout: Seconds to wait for callback (default: 120)

    Returns:
        Tuple of (code, error_message):
        - On success: (authorization_code, None)
        - On failure: (None, error_message)

    Example:
        code, error = run_oauth_flow(
            "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=http://localhost:8765"
        )
    """
    _OAuthCallbackHandler.code = None
    _OAuthCallbackHandler.state = None
    _OAuthCallbackHandler.error = None

    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.timeout = timeout

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    try:
        webbrowser.open(auth_url)
    except Exception:
        server.server_close()
        return None, f"Could not open browser. Visit manually:\n{auth_url}"

    thread.join(timeout=timeout)
    server.server_close()

    if _OAuthCallbackHandler.error:
        return None, _OAuthCallbackHandler.error
    if _OAuthCallbackHandler.code:
        return _OAuthCallbackHandler.code, None
    return None, "OAuth timed out."
