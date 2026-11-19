import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchScriptRunnerStatus,
  getScriptRunnerWebSocketUrl,
  getScriptStatusWebSocketUrl,
  stopManualScript,
} from '../services/dashboardApi'

export const DEFAULT_SCRIPT_TEMPLATE = `import rclpy
import DR_init

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

def run(node):
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_ABS, get_current_posx, movel, posx

    pos, sol = get_current_posx(ref=DR_BASE)
    print("현재 TCP 좌표:", pos, "sol:", sol)

    # 예시 이동:
    # movel(posx(350.90, -145.08, 250.0, 99.72, -174.32, 53.62), vel=50, acc=50, ref=DR_BASE, mod=DR_MV_MOD_ABS)

def main():
    rclpy.init()
    node = None
    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL
        node = rclpy.create_node("remote_test_script", namespace=ROBOT_ID)
        DR_init.__dsr__node = node
        run(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()

if __name__ == "__main__":
    main()
`

export function useScriptRunner() {
  const [code, setCode] = useState(DEFAULT_SCRIPT_TEMPLATE)
  const [timeoutSec, setTimeoutSec] = useState(120)
  const [autoEnter, setAutoEnter] = useState(true)
  const [isRunning, setIsRunning] = useState(false)
  const [remoteRunning, setRemoteRunning] = useState(false)
  const [remoteClientIp, setRemoteClientIp] = useState(null)
  const [outputLines, setOutputLines] = useState([])
  const [status, setStatus] = useState(null)

  const wsRef = useRef(null)
  const isBlockedByOther = remoteRunning && !isRunning

  useEffect(() => {
    let active = true
    let socket = null
    let connectTimer = null
    let reconnectTimer = null

    const applyRemoteStatus = (payload) => {
      if (!active || !payload || typeof payload.running !== 'boolean') return
      setRemoteRunning(payload.running)
      setRemoteClientIp(payload.running ? (payload.client_ip ?? null) : null)
    }

    fetchScriptRunnerStatus()
      .then(applyRemoteStatus)
      .catch(() => {})

    function connectStatus() {
      if (!active) return
      try {
        socket = new WebSocket(getScriptStatusWebSocketUrl())
      } catch {
        reconnectTimer = setTimeout(connectStatus, 2500)
        return
      }

      socket.onmessage = (event) => {
        try {
          applyRemoteStatus(JSON.parse(event.data))
        } catch {
          // ignore
        }
      }

      socket.onerror = () => {
        socket?.close()
      }

      socket.onclose = () => {
        if (!active) return
        reconnectTimer = setTimeout(connectStatus, 2500)
      }
    }

    function cleanupStatusSocket() {
      active = false
      if (connectTimer) {
        clearTimeout(connectTimer)
        connectTimer = null
      }
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      if (
        socket &&
        (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
      ) {
        socket.close(1000, 'Client closed')
      }
      socket = null
    }

    window.addEventListener('pagehide', cleanupStatusSocket)
    window.addEventListener('beforeunload', cleanupStatusSocket)
    connectTimer = setTimeout(connectStatus, 0)

    return () => {
      window.removeEventListener('pagehide', cleanupStatusSocket)
      window.removeEventListener('beforeunload', cleanupStatusSocket)
      cleanupStatusSocket()
    }
  }, [])

  const closeSocket = useCallback(() => {
    const socket = wsRef.current
    if (
      socket &&
      (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
    ) {
      socket.close(1000, 'Client closed')
    }
    wsRef.current = null
  }, [])

  useEffect(() => {
    const handleUnload = () => {
      closeSocket()
    }
    window.addEventListener('pagehide', handleUnload)
    window.addEventListener('beforeunload', handleUnload)
    return () => {
      window.removeEventListener('pagehide', handleUnload)
      window.removeEventListener('beforeunload', handleUnload)
      closeSocket()
    }
  }, [closeSocket])

  const appendLog = useCallback((stream, line) => {
    setOutputLines((prev) => [
      ...prev.slice(-299),
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2, 7)}`,
        stream,
        line,
      },
    ])
  }, [])

  const runScript = useCallback(() => {
    if (isRunning || isBlockedByOther) return
    closeSocket()
    setOutputLines([])
    setIsRunning(true)
    setStatus({ tone: 'running', message: '원격 파이썬 실행 연결 중...' })

    let socket = null
    let gotFinished = false

    try {
      socket = new WebSocket(getScriptRunnerWebSocketUrl())
      wsRef.current = socket
    } catch {
      setIsRunning(false)
      setStatus({ tone: 'error', message: '스크립트 실행 WebSocket 연결 실패' })
      return
    }

    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          code,
          timeout_sec: timeoutSec,
          auto_enter: autoEnter,
        }),
      )
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'started') {
          setStatus({ tone: 'running', message: data.message })
        } else if (data.type === 'log') {
          appendLog(data.stream || 'stdout', data.line ?? '')
        } else if (data.type === 'finished') {
          gotFinished = true
          setIsRunning(false)
          setStatus({
            tone: data.success ? 'success' : 'error',
            message: data.message || (data.success ? '실행 완료' : '실행 실패'),
          })
        }
      } catch {
        // ignore
      }
    }

    socket.onerror = () => {
      if (!gotFinished) {
        setIsRunning(false)
        setStatus({ tone: 'error', message: 'WebSocket 통신 오류가 발생했습니다.' })
      }
    }

    socket.onclose = () => {
      wsRef.current = null
      if (!gotFinished) {
        setIsRunning(false)
      }
    }
  }, [appendLog, autoEnter, closeSocket, code, isBlockedByOther, isRunning, timeoutSec])

  const stopScript = useCallback(async () => {
    const socket = wsRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'stop' }))
    }
    try {
      const res = await stopManualScript()
      setStatus({ tone: 'error', message: res.message })
    } catch (err) {
      setStatus({ tone: 'error', message: err.message || '중단 요청 실패' })
    } finally {
      setIsRunning(false)
    }
  }, [])

  const resetTemplate = useCallback(() => {
    setCode(DEFAULT_SCRIPT_TEMPLATE)
  }, [])

  const clearOutput = useCallback(() => {
    setOutputLines([])
    setStatus(null)
  }, [])

  return {
    code,
    setCode,
    timeoutSec,
    setTimeoutSec,
    autoEnter,
    setAutoEnter,
    isRunning,
    isBlockedByOther,
    remoteClientIp,
    outputLines,
    status,
    runScript,
    stopScript,
    resetTemplate,
    clearOutput,
  }
}
