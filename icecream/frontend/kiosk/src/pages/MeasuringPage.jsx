import { useEffect, useState } from 'react'
import { getMeasureWebSocketUrl } from '../services/kioskApi'
import { MEASURE_STEPS } from '../services/kioskMockService'

export function MeasuringPage({ preset, onComplete }) {
  const [stepIndex, setStepIndex] = useState(0)
  const [livePhase, setLivePhase] = useState('')
  const [liveProgress, setLiveProgress] = useState(null)
  const [liveMessage, setLiveMessage] = useState('')
  const [measureError, setMeasureError] = useState('')
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    let active = true
    let socket = null
    let fallbackTimers = []
    let fallbackStarted = false
    let receivedResult = false

    setMeasureError('')
    setStepIndex(0)
    setLivePhase('')
    setLiveProgress(null)
    setLiveMessage('')

    const startMockFallback = () => {
      if (!active || fallbackStarted) return
      fallbackStarted = true
      setStepIndex(0)
      setLivePhase('')
      setLiveProgress(null)
      setLiveMessage('')

      MEASURE_STEPS.forEach((_, idx) => {
        if (idx > 0) {
          fallbackTimers.push(setTimeout(() => active && setStepIndex(idx), idx * 650))
        }
      })

      fallbackTimers.push(
        setTimeout(() => {
          if (active) {
            onComplete({
              heightZ: preset.heightZ,
              diameter: preset.diameter,
            })
          }
        }, MEASURE_STEPS.length * 650 + 350),
      )
    }

    const closeSocket = () => {
      active = false
      fallbackTimers.forEach(clearTimeout)
      fallbackTimers = []
      if (
        socket &&
        (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
      ) {
        socket.close(1000, 'Client closed')
      }
      socket = null
    }

    window.addEventListener('pagehide', closeSocket)
    window.addEventListener('beforeunload', closeSocket)

    try {
      socket = new WebSocket(getMeasureWebSocketUrl())

      socket.onopen = () => {
        if (!active) return
        socket.send(
          JSON.stringify({
            measure_diameter: true,
            expected_diameter: preset.diameter,
          }),
        )
      }

      socket.onmessage = (event) => {
        if (!active) return
        try {
          const payload = JSON.parse(event.data)
          if (payload.type === 'feedback') {
            const phase = payload.current_phase || ''
            setLivePhase(phase)
            setLiveProgress(Math.round(Number(payload.progress_percent ?? 0)))
            const matchedIdx = MEASURE_STEPS.findIndex((s) => s.phase === phase)
            if (matchedIdx >= 0) {
              setStepIndex(matchedIdx)
              setLiveMessage(MEASURE_STEPS[matchedIdx].label)
            }
          } else if (payload.type === 'result') {
            receivedResult = true
            if (payload.success) {
              onComplete({
                heightZ:
                  Number(payload.measured_height_z) > 0
                    ? Number(payload.measured_height_z)
                    : preset.heightZ,
                diameter:
                  Number(payload.measured_diameter) > 0
                    ? Number(payload.measured_diameter)
                    : preset.diameter,
              })
            } else {
              setMeasureError(payload.message || '컵 측정에 실패했습니다.')
            }
          }
        } catch {
          setMeasureError('측정 응답 형식을 해석하지 못했습니다.')
        }
      }

      socket.onerror = () => {
        if (active && !receivedResult) {
          startMockFallback()
        }
      }

      socket.onclose = () => {
        if (active && !receivedResult && !fallbackStarted) {
          startMockFallback()
        }
      }
    } catch {
      startMockFallback()
    }

    return () => {
      window.removeEventListener('pagehide', closeSocket)
      window.removeEventListener('beforeunload', closeSocket)
      closeSocket()
    }
  }, [preset, onComplete, retryTick])

  const current = MEASURE_STEPS[stepIndex]
  const displayPhase = livePhase || current.phase
  const displayLabel = liveMessage || current.label
  const displayProgress = liveProgress ?? current.progress

  return (
    <section className="kiosk-card kiosk-card--center">
      <div className="pulse-ring" aria-hidden="true">
        <span className="pulse-ring__inner" />
      </div>

      <span className="step-pill">STEP 2 · 컵 규격 측정</span>
      <h1 className="kiosk-title">
        {measureError ? '컵 측정을 완료하지 못했습니다' : '컵 크기를 측정하고 있습니다'}
      </h1>
      <p className="kiosk-desc" style={measureError ? { color: '#a95d47' } : undefined}>
        {measureError || displayLabel}
      </p>

      <div className="progress-block">
        <div className="progress-block__meta">
          <span className="mono">{displayPhase}</span>
          <span className="tabular">{displayProgress}%</span>
        </div>
        <div className="progress-track">
          <div
            className="progress-fill"
            style={{ width: `${displayProgress}%` }}
          />
        </div>
      </div>

      <div className="phase-chips">
        {MEASURE_STEPS.map((item, idx) => (
          <span
            key={item.phase}
            className={`phase-chip ${idx <= stepIndex ? 'phase-chip--done' : ''}`}
          >
            {item.label}
          </span>
        ))}
      </div>

      {measureError && (
        <div className="kiosk-footer" style={{ justifyContent: 'center', marginTop: '12px' }}>
          <button
            type="button"
            className="primary-cta primary-cta--compact"
            onClick={() => setRetryTick((t) => t + 1)}
          >
            다시 측정
          </button>
          <button
            type="button"
            className="ghost-btn"
            onClick={() =>
              onComplete({
                heightZ: preset.heightZ,
                diameter: preset.diameter,
              })
            }
          >
            가상 크기로 계속 ({preset.heightZ}mm)
          </button>
        </div>
      )}
    </section>
  )
}
