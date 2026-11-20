import { useEffect, useRef, useState } from 'react'
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

const AUTO_RETRY_ELIGIBLE_STEPS = new Set(['', 'DISPATCHING', 'MOVE_CUP_HOLD'])
const MAX_SOFT_AUTO_RETRIES = 1

export function ScoopingPage({
  orderId,
  iceCreamType = 'CUP',
  scoops = [],
  softRetryCount = 0,
  isRetryingOrder = false,
  onRetrySoftOrder,
  onRemeasureCup,
  onComplete,
  onReset,
}) {
  const [scoopIdx, setScoopIdx] = useState(0)
  const [currentStep, setCurrentStep] = useState('DISPATCHING')
  const [progress, setProgress] = useState(0)
  const [statusMessage, setStatusMessage] = useState('로봇에 주문을 전달하는 중입니다.')
  const [errorMessage, setErrorMessage] = useState('')
  const [isAutoRetrying, setIsAutoRetrying] = useState(false)
  const lastStepRef = useRef('DISPATCHING')
  const onRetryRef = useRef(onRetrySoftOrder)
  const onCompleteRef = useRef(onComplete)
  const retryCountRef = useRef(softRetryCount)

  onRetryRef.current = onRetrySoftOrder
  onCompleteRef.current = onComplete
  retryCountRef.current = softRetryCount

  useEffect(() => {
    if (!orderId) return undefined

    let active = true
    let socket = null
    let completeTimer = null
    let retryTimer = null

    lastStepRef.current = 'DISPATCHING'
    setCurrentStep('DISPATCHING')
    setProgress(0)
    setErrorMessage('')
    setIsAutoRetrying(false)
    setStatusMessage(
      retryCountRef.current > 0
        ? `소프트 아이스크림 주문을 재시도 중입니다. (${retryCountRef.current}차 재시도)`
        : '로봇에 주문을 전달하는 중입니다.',
    )

    const closeSocket = () => {
      active = false
      if (completeTimer) {
        clearTimeout(completeTimer)
        completeTimer = null
      }
      if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
      if (
        socket &&
        (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
      ) {
        socket.close(1000, 'Client closed')
      }
      socket = null
    }

    const triggerFailure = (msg, { cancelled = false } = {}) => {
      const failedStep = lastStepRef.current
      const canAutoRetry =
        iceCreamType === 'SOFT' &&
        !cancelled &&
        typeof onRetryRef.current === 'function' &&
        retryCountRef.current < MAX_SOFT_AUTO_RETRIES &&
        AUTO_RETRY_ELIGIBLE_STEPS.has(failedStep)

      if (canAutoRetry) {
        setIsAutoRetrying(true)
        setErrorMessage('')
        setStatusMessage(`초기 단계 오류(${msg})로 1회 자동 재시도를 준비 중입니다.`)
        retryTimer = setTimeout(async () => {
          if (!active) return
          const res = await onRetryRef.current({ auto: true })
          if (active && res && !res.ok) {
            setIsAutoRetrying(false)
            setErrorMessage(res.message || msg)
          }
        }, 1200)
        return
      }

      setIsAutoRetrying(false)
      setErrorMessage(msg)
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
          lastStepRef.current = payload.current_step
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
            if (active) onCompleteRef.current()
          }, 400)
        } else if (
          orderStatus === 'FAILED' ||
          orderStatus === 'CANCELLED' ||
          (payload.type === 'result' && payload.success === false)
        ) {
          triggerFailure(payload.message || '제조 처리 중 오류가 발생했습니다.', {
            cancelled: orderStatus === 'CANCELLED',
          })
        }
      } catch {
        // ignore malformed frames
      }
    }

    socket.onerror = () => {
      if (active) {
        triggerFailure('진행 상태 WebSocket 연결에 실패했습니다.')
      }
    }

    return () => {
      window.removeEventListener('pagehide', closeSocket)
      window.removeEventListener('beforeunload', closeSocket)
      closeSocket()
    }
  }, [orderId, iceCreamType, scoops.length])

  const handleManualRetry = async () => {
    if (typeof onRetrySoftOrder !== 'function' || isRetryingOrder) return
    setErrorMessage('')
    setStatusMessage('소프트 아이스크림 제조를 다시 요청하고 있습니다.')
    const res = await onRetrySoftOrder({ auto: false })
    if (res && !res.ok) {
      setErrorMessage(res.message || '재시도 주문 요청에 실패했습니다.')
    }
  }

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
        {errorMessage
          ? '제조를 완료하지 못했습니다'
          : isAutoRetrying
            ? '자동 재시도를 준비하고 있습니다'
            : '아이스크림을 담고 있습니다'}
      </h1>
      <p className="kiosk-desc" style={errorMessage ? { color: '#a95d47' } : undefined}>
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
        <div
          className="kiosk-footer"
          style={{ justifyContent: 'center', marginTop: '12px', gap: '10px', flexWrap: 'wrap' }}
        >
          {isSoft && typeof onRetrySoftOrder === 'function' && (
            <button
              type="button"
              className="primary-cta primary-cta--compact"
              disabled={isRetryingOrder}
              onClick={handleManualRetry}
            >
              {isRetryingOrder ? '재시도 요청 중...' : '다시 시도'}
            </button>
          )}
          {isSoft && typeof onRemeasureCup === 'function' && (
            <button
              type="button"
              className="ghost-btn"
              disabled={isRetryingOrder}
              onClick={onRemeasureCup}
            >
              컵 다시 측정
            </button>
          )}
          <button
            type="button"
            className={isSoft ? 'ghost-btn' : 'primary-cta'}
            disabled={isRetryingOrder}
            onClick={onReset}
          >
            처음 화면으로
          </button>
        </div>
      )}
    </section>
  )
}
