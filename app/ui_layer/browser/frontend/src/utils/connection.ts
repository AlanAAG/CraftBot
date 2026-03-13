/**
 * Resolve the WebSocket URL for connecting to the backend.
 *
 * In development (Vite dev server), the proxy forwards /ws to the backend,
 * so we use window.location.host.
 *
 * In production (static server from PyInstaller binary), the frontend is
 * served on a different port than the backend. VITE_BACKEND_PORT is baked
 * in at build time so the frontend knows where to connect directly.
 */
export function getWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const backendPort = import.meta.env.VITE_BACKEND_PORT
  if (backendPort && backendPort !== window.location.port) {
    // Connect directly to backend port
    return `${protocol}//${window.location.hostname}:${backendPort}/ws`
  }
  // Dev mode: proxy handles it
  return `${protocol}//${window.location.host}/ws`
}

/**
 * Resolve the base URL for API requests to the backend.
 */
export function getApiBaseUrl(): string {
  const backendPort = import.meta.env.VITE_BACKEND_PORT
  if (backendPort && backendPort !== window.location.port) {
    return `${window.location.protocol}//${window.location.hostname}:${backendPort}`
  }
  return ''
}
