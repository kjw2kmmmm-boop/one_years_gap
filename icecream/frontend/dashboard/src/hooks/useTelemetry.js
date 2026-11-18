import { useEffect, useState } from 'react'
import { fetchTelemetry, getTelemetryWebSocketUrl } from '../services/dashboardApi'

const INITIAL_TELEMETRY = {
  connected: false,
  timestamp: 0,
  robot_mode: 'MANUAL',
  is_emergency_stopped: false,
  is_robot_moving: false,
  current_tcp_pose: [0, 0, 0, 0, 0, 0],
  joint_torques: [0, 0, 0, 0, 0, 0],
  tool_force_z: 0,
  system_state: 'IDLE',
  current_order_id: '',
  current_order_progress: 0,
  latest_cup_height_z: 0,
  cup_stock_warning: false,
  active_error_code: 0,
}

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState(INITIAL_TELEMETRY)
  const [wsStatus, setWsStatus] = useState('connecting')

  useEffect(() => {
    let active = true
    let socket = null
    let reconnectTimer = null

    fetchTelemetry()
      .then((snapshot) => {
        if (active && snapshot) {
          setTelemetry(snapshot)
        }
      })
      .catch(() => {})

    function connect() {
      if (!active) return
      setWsStatus('connecting')

      try {
        socket = new WebSocket(getTelemetryWebSocketUrl())
      } catch {
        setWsStatus('disconnected')
        reconnectTimer = setTimeout(connect, 2500)
        return
      }

      socket.onopen = () => {
        if (active) setWsStatus('connected')
      }

      socket.onmessage = (event) => {
        if (!active) return
        try {
          const payload = JSON.parse(event.data)
          setTelemetry(payload)
        } catch {
          // ignore malformed frames
        }
      }

      socket.onerror = () => {
        socket?.close()
      }

      socket.onclose = () => {
        if (!active) return
        setWsStatus('disconnected')
        reconnectTimer = setTimeout(connect, 2500)
      }
    }

    connect()

    return () => {
      active = false
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (socket) socket.close()
    }
  }, [])

  return {
    telemetry,
    wsStatus,
  }
}
