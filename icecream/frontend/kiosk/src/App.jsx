import { useCallback, useMemo, useState } from 'react'
import { CompletePage } from './pages/CompletePage'
import { CupInsertPage } from './pages/CupInsertPage'
import { FlavorSelectPage } from './pages/FlavorSelectPage'
import { MeasuringPage } from './pages/MeasuringPage'
import { ScoopingPage } from './pages/ScoopingPage'
import { TypeSelectPage } from './pages/TypeSelectPage'
import {
  CUP_PRESETS,
  calculateMaxScoops,
  createMockOrderId,
} from './services/kioskMockService'

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
  const [measuredCup, setMeasuredCup] = useState({ heightZ: 115.0, diameter: 90.0 })
  const [selectedScoops, setSelectedScoops] = useState([])
  const [orderId, setOrderId] = useState('')

  const activePreset = useMemo(
    () => CUP_PRESETS.find((item) => item.id === presetId) ?? CUP_PRESETS[1],
    [presetId],
  )

  const maxScoops = calculateMaxScoops(measuredCup.heightZ)
  const currentStepIdx = STEPS.findIndex((s) => s.id === step)

  const handleMeasureComplete = useCallback((result) => {
    setMeasuredCup(result)
    setStep('SELECT_TYPE')
  }, [])

  const handleConfirmScoops = useCallback((scoops) => {
    setSelectedScoops(scoops)
    setOrderId(createMockOrderId())
    setStep('SCOOPING')
  }, [])

  const handleScoopComplete = useCallback(() => {
    setStep('COMPLETE')
  }, [])

  const handleReset = useCallback(() => {
    setSelectedScoops([])
    setOrderId('')
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
              onSelectCupIceCream={() => setStep('SELECT_FLAVOR')}
              onBack={() => setStep('INSERT_CUP')}
            />
          )}

          {step === 'SELECT_FLAVOR' && (
            <FlavorSelectPage
              measuredCup={measuredCup}
              maxScoops={maxScoops}
              onConfirm={handleConfirmScoops}
              onBack={() => setStep('SELECT_TYPE')}
            />
          )}

          {step === 'SCOOPING' && (
            <ScoopingPage
              orderId={orderId}
              scoops={selectedScoops}
              onComplete={handleScoopComplete}
            />
          )}

          {step === 'COMPLETE' && (
            <CompletePage
              orderId={orderId}
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
