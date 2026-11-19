import { useEffect, useState } from 'react'
import { getOrderProgressWebSocketUrl } from '../services/kioskApi'
import { FLAVORS } from '../services/kioskMockService'

const SOFT_STEPS = [
  { id: 'MOVE_CUP_HOLD', label: '1단계 · 컵 홀드 위치 이동' },
  { id: 'GRIPPER_GRAB', label: '2단계 · 그립으로 컵 잡기' },
  { id: 'MOVE_CUP_MIDDLE', label: '3단계 · 중앙(스파이럴) 위치 이동' },
  { id: 'MOVE_CUP_SPIRAL', label: '4단계 · 스파이럴 제조' },
  { id: 'GRIPPER_RELEASE', label: '5단계 · 컵 놓기 (그리퍼 열기)' },
  { id: 'MOVE_HOME', label: '6단계 · HOME 복귀' },
]

export function ScoopingPage({
  orderId,
  iceCreamType = 'CUP',
  scoops = [],
  onComplete,
  onReset,
}) {
  const [scoopIdx, setScoopIdx] = useState(0)
  const [currentStep, setCurrentStep] = useState('DISPATCHING')
  const [progress, setProgress] = useState(0)
  const [statusMessage, setStatusMessage] = useState('로봇에 주문을 전달하는 중입니다.')
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    if (!orderId) return undefined

    let active = true
    let socket = null
    let completeTimer = null

    const closeSocket = () => {
      active = false
      if (completeTimer) {
        clearTimeout(completeTimer)
        completeTimer = null
      }
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

    socket = new WebSocket(getOrderProgressWebSocketUrl(orderId))

    socket.onmessage = (event) => {
      if (!active) return
      try {
        const payload = JSON.parse(event.data)
        const orderStatus = payload.order_status || ''

        if (payload.current_step) {
          setCurrentStep(payload.current_step)
        }
        if (payload.progress_percent != null) {
          setProgress(Math.max(0, Math.min(100, Math.round(Number(payload.progress_percent)))))
        }
        if (payload.current_scoop_index > 0 && scoops.length > 0) {
          setScoopIdx(Math.min(scoops.length - 1, Number(payload.current_scoop_index) - 1))
        }
        if (payload.message) {
          setStatusMessage(payload.message)
        }

        if (orderStatus === 'COMPLETED' || (payload.type === 'result' && payload.success)) {
          setProgress(100)
          completeTimer = setTimeout(() => {
            if (active) onComplete()
          }, 400)
        } else if (
          orderStatus === 'FAILED' ||
          orderStatus === 'CANCELLED' ||
          (payload.type === 'result' && payload.success === false)
        ) {
          setErrorMessage(payload.message || '제조 처리 중 오류가 발생했습니다.')
        }
      } catch {
        // ignore malformed frames
      }
    }

    socket.onerror = () => {
      if (active) {
        setErrorMessage('진행 상태 WebSocket 연결에 실패했습니다.')
      }
    }

    return () => {
      window.removeEventListener('pagehide', closeSocket)
      window.removeEventListener('beforeunload', closeSocket)
      closeSocket()
    }
  }, [orderId, scoops.length, onComplete])

  const isSoft = iceCreamType === 'SOFT'
  const currentFlavorId = scoops[scoopIdx]
  const currentFlavor = FLAVORS.find((f) => f.id === currentFlavorId)
  const softActiveIdx = SOFT_STEPS.findIndex((s) => s.id === currentStep)

  return (
    <section className="kiosk-card kiosk-card--center">
      <div className="pulse-ring" aria-hidden="true">
        <span
          className="pulse-ring__inner"
          style={
            currentFlavor ? { backgroundColor: currentFlavor.swatch } : undefined
          }
        />
      </div>

      <span className="step-pill">STEP 5 · 제조 중 ({orderId})</span>
      <h1 className="kiosk-title">
        {errorMessage ? '제조를 완료하지 못했습니다' : '아이스크림을 담고 있습니다'}
      </h1>
      <p className="kiosk-desc">
        {isSoft ? (
          <strong>소프트 아이스크림</strong>
        ) : (
          <strong>
            {scoopIdx + 1} / {scoops.length} 스쿱 ({currentFlavor?.name})
          </strong>
        )}{' '}
        · {errorMessage || statusMessage}
      </p>

      <div className="progress-block">
        <div className="progress-block__meta">
          <span className="mono">{currentStep}</span>
          <span className="tabular">{progress}%</span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="scoop-progress-list">
        {isSoft
          ? SOFT_STEPS.map((item, idx) => {
              const status =
                progress >= 100 || (softActiveIdx >= 0 && idx < softActiveIdx)
                  ? '완료'
                  : idx === softActiveIdx
                    ? errorMessage
                      ? '중단'
                      : '제조 중'
                    : '대기'
              return (
                <div
                  key={item.id}
                  className={`scoop-progress-item ${
                    !errorMessage && idx === softActiveIdx
                      ? 'scoop-progress-item--active'
                      : ''
                  }`}
                >
                  <span
                    className="scoop-progress-item__dot"
                    style={{ backgroundColor: '#4c685b' }}
                  />
                  <span>{item.label}</span>
                  <span className="scoop-progress-item__status">{status}</span>
                </div>
              )
            })
          : scoops.map((flavorId, idx) => {
              const flavor = FLAVORS.find((f) => f.id === flavorId)
              const status = errorMessage
                ? idx === scoopIdx
                  ? '중단'
                  : idx < scoopIdx
                    ? '완료'
                    : '대기'
                : progress >= 100 || idx < scoopIdx
                  ? '완료'
                  : idx === scoopIdx
                    ? '제조 중'
                    : '대기'
              return (
                <div
                  key={idx}
                  className={`scoop-progress-item ${
                    !errorMessage && idx === scoopIdx
                      ? 'scoop-progress-item--active'
                      : ''
                  }`}
                >
                  <span
                    className="scoop-progress-item__dot"
                    style={{ backgroundColor: flavor?.swatch }}
                  />
                  <span>
                    {idx + 1}번 · {flavor?.name}
                  </span>
                  <span className="scoop-progress-item__status">{status}</span>
                </div>
              )
            })}
      </div>

      {errorMessage && (
        <button type="button" className="primary-cta" onClick={onReset}>
          처음 화면으로
        </button>
      )}
    </section>
  )
}
