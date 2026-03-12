import React, { createContext, useContext, useEffect, useRef, useState, useCallback, ReactNode } from 'react'
import type { ChatMessage, ActionItem, AgentStatus, InitialState, WSMessage, DashboardMetrics, TaskCancelResponse, Attachment, FilteredDashboardMetrics, MetricsTimePeriod } from '../types'

// Pending attachment type for upload
interface PendingAttachment {
  name: string
  type: string
  size: number
  content: string  // base64
}

interface WebSocketState {
  connected: boolean
  messages: ChatMessage[]
  actions: ActionItem[]
  status: AgentStatus
  guiMode: boolean
  currentTask: { id: string; name: string } | null
  footageUrl: string | null
  dashboardMetrics: DashboardMetrics | null
  filteredMetricsCache: Record<MetricsTimePeriod, FilteredDashboardMetrics | null>
  cancellingTaskId: string | null
}

interface WebSocketContextType extends WebSocketState {
  sendMessage: (content: string, attachments?: PendingAttachment[]) => void
  sendCommand: (command: string) => void
  clearMessages: () => void
  cancelTask: (taskId: string) => void
  openFile: (path: string) => void
  openFolder: (path: string) => void
  requestFilteredMetrics: (period: MetricsTimePeriod) => void
}

const defaultState: WebSocketState = {
  connected: false,
  messages: [],
  actions: [],
  status: {
    state: 'idle',
    message: 'Connecting...',
    loading: false,
  },
  guiMode: false,
  currentTask: null,
  footageUrl: null,
  dashboardMetrics: null,
  filteredMetricsCache: {
    '1h': null,
    '1d': null,
    '1w': null,
    '1m': null,
    'total': null,
  },
  cancellingTaskId: null,
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined)

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WebSocketState>(defaultState)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const isConnectingRef = useRef<boolean>(false)
  const reconnectCountRef = useRef<number>(0)
  const maxReconnectAttemptsRef = useRef<number>(10)

  const connect = useCallback(() => {
    // Prevent duplicate connections (React StrictMode calls useEffect twice)
    if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }
    isConnectingRef.current = true

    // Close any existing connection before creating new one
    if (wsRef.current) {
      try {
        wsRef.current.close()
      } catch (e) {
        // Connection already closed
      }
      wsRef.current = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[WS] Connected')
        isConnectingRef.current = false
        reconnectCountRef.current = 0  // Reset reconnect counter on successful connection
        setState(prev => ({ ...prev, connected: true }))
      }

      ws.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data)
          handleMessage(msg)
        } catch (err) {
          console.error('[WS] Failed to parse message:', err, 'Raw:', event.data)
        }
      }

      ws.onclose = () => {
        console.log('[WS] Disconnected, reconnectCount =', reconnectCountRef.current)
        isConnectingRef.current = false
        setState(prev => ({
          ...prev,
          connected: false,
          status: { ...prev.status, message: 'Disconnected. Reconnecting...' },
        }))

        // Immediate first retry, then exponential backoff
        let reconnectDelay = 500
        if (reconnectCountRef.current > 0) {
          // Exponential backoff after first disconnect
          reconnectDelay = Math.min(1000 * Math.pow(1.5, reconnectCountRef.current - 1), 30000)
        }
        reconnectCountRef.current += 1

        if (reconnectCountRef.current <= maxReconnectAttemptsRef.current) {
          console.log(`[WS] Reconnection attempt ${reconnectCountRef.current}/${maxReconnectAttemptsRef.current} in ${reconnectDelay}ms`)
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect()
          }, reconnectDelay)
        } else {
          console.error(`[WS] Failed to reconnect after ${maxReconnectAttemptsRef.current} attempts`)
          setState(prev => ({
            ...prev,
            status: { ...prev.status, message: 'Connection failed - please refresh the page' },
          }))
        }
      }

      ws.onerror = (err) => {
        console.error('[WS] Error:', err, '(Error object might be limited on some browsers)')
        // Note: On some browsers, WebSocket error events don't contain detailed info
        // The onclose handler will be called after onerror
      }
    } catch (err) {
      console.error('[WS] Failed to create WebSocket:', err)
      isConnectingRef.current = false
      // Retry connection
      reconnectCountRef.current += 1
      const reconnectDelay = Math.min(1000 * Math.pow(1.5, reconnectCountRef.current), 30000)
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, reconnectDelay)
    }
  }, [])

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'init': {
        const data = msg.data as unknown as InitialState
        setState(prev => ({
          ...prev,
          messages: data.messages || [],
          actions: data.actions || [],
          status: {
            state: data.agentState || 'idle',
            message: data.status || 'Ready',
            loading: false,
          },
          guiMode: data.guiMode || false,
          currentTask: data.currentTask || null,
          dashboardMetrics: data.dashboardMetrics || null,
        }))
        break
      }

      case 'chat_message': {
        const message = msg.data as unknown as ChatMessage
        setState(prev => ({
          ...prev,
          messages: [...prev.messages, message],
        }))
        break
      }

      case 'chat_clear':
        setState(prev => ({ ...prev, messages: [] }))
        break

      case 'action_add': {
        const action = msg.data as unknown as ActionItem
        setState(prev => {
          // Prevent duplicate items by ID only
          const existingItem = prev.actions.find(a => a.id === action.id)
          if (existingItem) {
            // Update existing item's status if different
            if (existingItem.status !== action.status) {
              return {
                ...prev,
                actions: prev.actions.map(a =>
                  a.id === action.id ? { ...a, status: action.status } : a
                ),
              }
            }
            return prev // No change needed
          }
          return {
            ...prev,
            actions: [...prev.actions, action],
          }
        })
        break
      }

      case 'action_update': {
        const { id, status, duration, output, error } = msg.data as {
          id: string
          status: string
          duration?: number
          output?: string
          error?: string
        }
        setState(prev => ({
          ...prev,
          actions: prev.actions.map(a =>
            a.id === id
              ? { ...a, status: status as ActionItem['status'], duration, output, error }
              : a
          ),
        }))
        break
      }

      case 'action_remove': {
        const { id } = msg.data as { id: string }
        setState(prev => ({
          ...prev,
          actions: prev.actions.filter(a => a.id !== id),
        }))
        break
      }

      case 'action_clear':
        setState(prev => ({ ...prev, actions: [] }))
        break

      case 'status_update': {
        const { message, loading } = msg.data as { message: string; loading: boolean }
        setState(prev => ({
          ...prev,
          status: { ...prev.status, message, loading },
        }))
        break
      }

      case 'footage_update': {
        const { image } = msg.data as { image: string }
        setState(prev => ({ ...prev, footageUrl: image }))
        break
      }

      case 'footage_clear':
        setState(prev => ({ ...prev, footageUrl: null }))
        break

      case 'footage_visibility': {
        const { visible } = msg.data as { visible: boolean }
        setState(prev => ({ ...prev, guiMode: visible }))
        break
      }

      case 'dashboard_metrics': {
        const metrics = msg.data as unknown as DashboardMetrics
        setState(prev => ({ ...prev, dashboardMetrics: metrics }))
        break
      }

      case 'dashboard_filtered_metrics': {
        const metrics = msg.data as unknown as FilteredDashboardMetrics
        // Cache by period so each card can have independent data
        setState(prev => ({
          ...prev,
          filteredMetricsCache: {
            ...prev.filteredMetricsCache,
            [metrics.period]: metrics,
          },
        }))
        break
      }

      case 'task_cancel_response': {
        const response = msg.data as unknown as TaskCancelResponse
        if (response.success) {
          // Update the task status to cancelled
          setState(prev => ({
            ...prev,
            cancellingTaskId: null,
            actions: prev.actions.map(a =>
              a.id === response.taskId
                ? { ...a, status: 'cancelled' as const }
                : a
            ),
          }))
        } else {
          // Cancel failed, reset cancelling state
          setState(prev => ({ ...prev, cancellingTaskId: null }))
        }
        break
      }
    }
  }, [])

  useEffect(() => {
    connect()

    return () => {
      // Reset connecting flag on cleanup
      isConnectingRef.current = false
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  const sendMessage = useCallback((content: string, attachments?: PendingAttachment[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'message',
        content,
        attachments: attachments || []
      }))
    }
  }, [])

  const sendCommand = useCallback((command: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'command', command }))
    }
  }, [])

  const clearMessages = useCallback(() => {
    setState(prev => ({ ...prev, messages: [] }))
  }, [])

  const cancelTask = useCallback((taskId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setState(prev => ({ ...prev, cancellingTaskId: taskId }))
      wsRef.current.send(JSON.stringify({ type: 'task_cancel', taskId }))
    }
  }, [])

  const openFile = useCallback((path: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'open_file', path }))
    }
  }, [])

  const openFolder = useCallback((path: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'open_folder', path }))
    }
  }, [])

  const requestFilteredMetrics = useCallback((period: MetricsTimePeriod) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'dashboard_metrics_filter',
        period
      }))
    }
  }, [])

  return (
    <WebSocketContext.Provider
      value={{
        ...state,
        sendMessage,
        sendCommand,
        clearMessages,
        cancelTask,
        openFile,
        openFolder,
        requestFilteredMetrics,
      }}
    >
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocket() {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider')
  }
  return context
}
