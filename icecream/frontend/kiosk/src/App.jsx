import { useCallback, useMemo, useRef, useState } from 'react'
import { CompletePage } from './pages/CompletePage'
import { CupInsertPage } from './pages/CupInsertPage'
import { FlavorSelectPage } from './pages/FlavorSelectPage'
import { MeasuringPage } from './pages/MeasuringPage'
import { ScoopingPage } from './pages/ScoopingPage'
import { TypeSelectPage } from './pages/TypeSelectPage'
import {
  CUP_PRESETS,
  calculateMaxScoops,
} from './services/kioskMockService'
import { createOrder } from './services/kioskApi'

const STEPS = [
  { id: 'INSERT_CUP', label: '컵 투입' },
  { id: 'MEASURING', label: '컵 측정' },
  { id: 'SELECT_TYPE', label: '유형 선택' },
  { id: 'SELECT_FLAVOR', label: '맛 선택' },
  { id: 'SCOOPING', label: '제조 중' },
  { id: 'COMPLETE', label: '완료' },
]

export default function App() {
  const [step, setStep] = useState('INSERT_CUP')
  const [presetId, setPresetId] = useState('medium')
  const [iceCreamType, setIceCreamType] = useState('CUP')
  const [measuredCup, setMeasuredCup] = useState({ heightZ: 115.0, diameter: 90.0 })
  const [selectedScoops, setSelectedScoops] = useState([])
  const [orderId, setOrderId] = useState('')
  const [softRetryCount, setSoftRetryCount] = useState(0)
  const [isSubmittingOrder, setIsSubmittingOrder] = useState(false)
  const [orderSubmitError, setOrderSubmitError] = useState('')
  const isSubmittingRef = useRef(false)

  const activePreset = useMemo(
    () => CUP_PRESETS.find((item) => item.id === presetId) ?? CUP_PRESETS[1],
    [presetId],
  )

  const maxScoops = calculateMaxScoops(measuredCup.heightZ)
  const currentStepIdx = STEPS.findIndex((s) => s.id === step)

  const handleMeasureComplete = useCallback((result) => {
    setMeasuredCup(result)
    setOrderSubmitError('')
    setStep('SELECT_TYPE')
  }, [])

  const handleSkipMeasure = useCallback(() => {
    setMeasuredCup({
      heightZ: activePreset.heightZ,
      diameter: activePreset.diameter,
    })
    setOrderSubmitError('')
    setStep('SELECT_TYPE')
  }, [activePreset])

  const submitOrder = useCallback(
    async (type, scoops, { maxDispatchRetries = 0, retryCount = 0 } = {}) => {
      if (isSubmittingRef.current) return { ok: false, message: '주문 처리 중입니다.' }
      isSubmittingRef.current = true
      setIsSubmittingOrder(true)
      setOrderSubmitError('')
      try {
        let lastError = null
        for (let attempt = 0; attempt <= maxDispatchRetries; attempt += 1) {
          try {
            const created = await createOrder({
              ice_cream_type: type,
              cup_height_z: measuredCup.heightZ,
              cup_diameter: measuredCup.diameter,
              scoops,
            })
            setIceCreamType(type)
            setSelectedScoops(scoops)
            setSoftRetryCount(retryCount)
            setOrderId(created.order_code)
            setStep('SCOOPING')
            return { ok: true, orderCode: created.order_code }
          } catch (err) {
            lastError = err
            if (attempt < maxDispatchRetries) {
              await new Promise((resolve) => setTimeout(resolve, 800))
            }
          }
        }
        const message = lastError?.message || '주문을 서버에 저장하지 못했습니다.'
        setOrderSubmitError(message)
        return { ok: false, message }
      } finally {
        isSubmittingRef.current = false
        setIsSubmittingOrder(false)
      }
    },
    [measuredCup],
  )

  const handleSelectSoftIceCream = useCallback(() => {
    submitOrder('SOFT', [], { maxDispatchRetries: 1, retryCount: 0 })
  }, [submitOrder])

  const handleRetrySoftOrder = useCallback(
    ({ auto = false } = {}) => {
      const nextRetryCount = auto ? softRetryCount + 1 : softRetryCount
      return submitOrder('SOFT', [], {
        maxDispatchRetries: 1,
        retryCount: nextRetryCount,
      })
    },
    [softRetryCount, submitOrder],
  )

  const handleRemeasureCup = useCallback(() => {
    setOrderId('')
    setSoftRetryCount(0)
    setOrderSubmitError('')
    setStep('MEASURING')
  }, [])

  const handleConfirmScoops = useCallback(
    (scoops) => {
      submitOrder('CUP', scoops, { retryCount: 0 })
    },
    [submitOrder],
  )

  const handleScoopComplete = useCallback(() => {
    setStep('COMPLETE')
  }, [])

  const handleReset = useCallback(() => {
    setIceCreamType('CUP')
    setSelectedScoops([])
    setOrderId('')
    setSoftRetryCount(0)
    setOrderSubmitError('')
    setStep('INSERT_CUP')
  }, [])

  return (
    <div className="kiosk-shell">
      <div className="kiosk-frame">
        <header className="kiosk-header">
          <div>
            <p className="kiosk-brand">ATELIER GELATO · COBOT KIOSK</p>
            <span className="kiosk-mock-tag">MOCKUP FLOW</span>
          </div>

          <nav className="stepper" aria-label="주문 진행 단계">
            {STEPS.map((item, idx) => (
              <div
                key={item.id}
                className={`stepper__item ${
                  idx === currentStepIdx
                    ? 'stepper__item--current'
                    : idx < currentStepIdx
                      ? 'stepper__item--done'
                      : ''
                }`}
              >
                <span className="stepper__num">{idx + 1}</span>
                <span className="stepper__label">{item.label}</span>
              </div>
            ))}
          </nav>
        </header>

        <main className="kiosk-main">
          {step === 'INSERT_CUP' && (
            <CupInsertPage
              selectedPresetId={presetId}
              onSelectPreset={setPresetId}
              onStartMeasure={() => setStep('MEASURING')}
              onSkipMeasure={handleSkipMeasure}
            />
          )}

          {step === 'MEASURING' && (
            <MeasuringPage
              preset={activePreset}
              onComplete={handleMeasureComplete}
            />
          )}

          {step === 'SELECT_TYPE' && (
            <TypeSelectPage
              measuredCup={measuredCup}
              maxScoops={maxScoops}
              isSubmitting={isSubmittingOrder}
              submitError={orderSubmitError}
              onSelectSoftIceCream={handleSelectSoftIceCream}
              onSelectCupIceCream={() => {
                setIceCreamType('CUP')
                setOrderSubmitError('')
                setStep('SELECT_FLAVOR')
              }}
              onBack={() => setStep('INSERT_CUP')}
            />
          )}

          {step === 'SELECT_FLAVOR' && (
            <FlavorSelectPage
              measuredCup={measuredCup}
              maxScoops={maxScoops}
              isSubmitting={isSubmittingOrder}
              submitError={orderSubmitError}
              onConfirm={handleConfirmScoops}
              onBack={() => setStep('SELECT_TYPE')}
            />
          )}

          {step === 'SCOOPING' && (
            <ScoopingPage
              orderId={orderId}
              iceCreamType={iceCreamType}
              scoops={selectedScoops}
              softRetryCount={softRetryCount}
              isRetryingOrder={isSubmittingOrder}
              onRetrySoftOrder={handleRetrySoftOrder}
              onRemeasureCup={handleRemeasureCup}
              onComplete={handleScoopComplete}
              onReset={handleReset}
            />
          )}

          {step === 'COMPLETE' && (
            <CompletePage
              orderId={orderId}
              iceCreamType={iceCreamType}
              measuredCup={measuredCup}
              scoops={selectedScoops}
              onReset={handleReset}
            />
          )}
        </main>
      </div>
    </div>
  )
}
