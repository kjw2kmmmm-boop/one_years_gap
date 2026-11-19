import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getManualJogWebSocketUrl,
  manualSetMode,
  manualSetSpeed,
  manualStep,
  manualStop,
} from '../services/dashboardApi'

export function useManualControl() {
  const [controlMode, setControlMode] = useState('step') // 'step' | 'jog'
  const [space, setSpace] = useState('task_base') // 'task_base' | 'task_tool' | 'joint'
  const [stepSizeMm, setStepSizeMm] = useState(5)
  const [stepSizeDeg, setStepSizeDeg] = useState(5)
  const [speedPct, setSpeedPct] = useState(20)
  const [isBusy, setIsBusy] = useState(false)
  const [activeJogKey, setActiveJogKey] = useState(null)
  const [feedback, setFeedback] = useState(null)

  const wsRef = useRef(null)
  const heartbeatRef = useRef(null)
  const isJoggingRef = useRef(false)

  const stopHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current)
      heartbeatRef.current = null
    }
  }, [])

  const stopJog = useCallback(() => {
    stopHeartbeat()
    const wasJogging = isJoggingRef.current
    isJoggingRef.current = false
    setActiveJogKey(null)
    if (wasJogging && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'jog_stop' }))
    }
  }, [stopHeartbeat])

  useEffect(() => {
    if (controlMode !== 'jog') {
      stopJog()
      if (wsRef.current) {
        wsRef.current.close(1000, 'Switched to step mode')
        wsRef.current = null
      }
      return undefined
    }

    let active = true
    let socket = null

    try {
      socket = new WebSocket(getManualJogWebSocketUrl())
      wsRef.current = socket

      socket.onmessage = (event) => {
        if (!active) return
        try {
          const data = JSON.parse(event.data)
          if (data.message && !data.success) {
            setFeedback({ tone: 'error', message: data.message })
          }
        } catch {
          // ignore
        }
      }

      socket.onclose = () => {
        if (active) {
          stopHeartbeat()
          isJoggingRef.current = false
          setActiveJogKey(null)
        }
      }
    } catch {
      setFeedback({ tone: 'error', message: '조그 WebSocket 연결 실패' })
    }

    const handleGlobalStop = () => {
      stopJog()
    }
    const handleUnload = () => {
      active = false
      stopJog()
      if (
        socket &&
        (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
      ) {
        socket.close(1000, 'Client closed')
      }
    }

    window.addEventListener('blur', handleGlobalStop)
    window.addEventListener('pointerup', handleGlobalStop)
    window.addEventListener('pointercancel', handleGlobalStop)
    window.addEventListener('pagehide', handleUnload)
    window.addEventListener('beforeunload', handleUnload)

    return () => {
      active = false
      window.removeEventListener('blur', handleGlobalStop)
      window.removeEventListener('pointerup', handleGlobalStop)
      window.removeEventListener('pointercancel', handleGlobalStop)
      window.removeEventListener('pagehide', handleUnload)
      window.removeEventListener('beforeunload', handleUnload)
      handleUnload()
      wsRef.current = null
    }
  }, [controlMode, stopHeartbeat, stopJog])

  const startJog = useCallback(
    (axisIdx, sign, key) => {
      if (controlMode !== 'jog') return
      const socket = wsRef.current
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        setFeedback({ tone: 'error', message: '조그 WebSocket이 연결되지 않았습니다.' })
        return
      }

      const isJoint = space === 'joint'
      const jogAxis = isJoint ? axisIdx : axisIdx + 6
      const moveReference = space === 'task_tool' ? 1 : 0
      const signedSpeed = sign * speedPct

      isJoggingRef.current = true
      setActiveJogKey(key)
      setFeedback({ tone: 'neutral', message: `연속 조그 이동 중 (${signedSpeed > 0 ? '+' : ''}${signedSpeed}%)` })

      socket.send(
        JSON.stringify({
          type: 'jog_start',
          jog_axis: jogAxis,
          move_reference: moveReference,
          speed: signedSpeed,
        }),
      )

      stopHeartbeat()
      heartbeatRef.current = setInterval(() => {
        if (isJoggingRef.current && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'heartbeat' }))
        }
      }, 120)
    },
    [controlMode, space, speedPct, stopHeartbeat],
  )

  const triggerStep = useCallback(
    async (axisIdx, sign) => {
      if (isBusy) return
      setIsBusy(true)
      const isJoint = space === 'joint'
      const isRotational = !isJoint && axisIdx >= 3
      const magnitude = isJoint || isRotational ? stepSizeDeg : stepSizeMm
      const delta = sign * magnitude

      try {
        const res = await manualStep({
          space: isJoint ? 'joint' : 'task',
          axis: axisIdx,
          delta,
          move_reference: space === 'task_tool' ? 1 : 0,
          speed_pct: speedPct,
        })
        setFeedback({ tone: 'success', message: res.message })
      } catch (err) {
        setFeedback({ tone: 'error', message: err.message || '스텝 이동 실패' })
      } finally {
        setIsBusy(false)
      }
    },
    [isBusy, space, stepSizeDeg, stepSizeMm, speedPct],
  )

  const triggerStop = useCallback(async () => {
    stopJog()
    try {
      const res = await manualStop(1)
      setFeedback({ tone: 'success', message: res.message })
    } catch (err) {
      setFeedback({ tone: 'error', message: err.message || '정지 요청 실패' })
    }
  }, [stopJog])

  const changeOperationSpeed = useCallback(async (speed) => {
    try {
      const res = await manualSetSpeed(speed)
      setFeedback({ tone: 'success', message: res.message })
    } catch (err) {
      setFeedback({ tone: 'error', message: err.message || '속도 설정 실패' })
    }
  }, [])

  const changeRobotMode = useCallback(async (mode) => {
    try {
      const res = await manualSetMode(mode)
      setFeedback({ tone: 'success', message: res.message })
    } catch (err) {
      setFeedback({ tone: 'error', message: err.message || '모드 전환 실패' })
    }
  }, [])

  return {
    controlMode,
    setControlMode,
    space,
    setSpace,
    stepSizeMm,
    setStepSizeMm,
    stepSizeDeg,
    setStepSizeDeg,
    speedPct,
    setSpeedPct,
    isBusy,
    activeJogKey,
    feedback,
    setFeedback,
    startJog,
    stopJog,
    triggerStep,
    triggerStop,
    changeOperationSpeed,
    changeRobotMode,
  }
}
