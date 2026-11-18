import { useEffect, useState } from 'react'
import { FLAVORS, SCOOP_STAGES } from '../services/kioskMockService'

export function ScoopingPage({ orderId, scoops, onComplete }) {
  const [scoopIdx, setScoopIdx] = useState(0)
  const [stageIdx, setStageIdx] = useState(0)

  const totalSteps = scoops.length * SCOOP_STAGES.length

  useEffect(() => {
    setScoopIdx(0)
    setStageIdx(0)

    let tick = 0
    const interval = setInterval(() => {
      tick += 1
      if (tick >= totalSteps) {
        clearInterval(interval)
        setTimeout(onComplete, 400)
        return
      }
      setScoopIdx(Math.floor(tick / SCOOP_STAGES.length))
      setStageIdx(tick % SCOOP_STAGES.length)
    }, 550)

    return () => clearInterval(interval)
  }, [totalSteps, onComplete])

  const completedSteps = scoopIdx * SCOOP_STAGES.length + stageIdx + 1
  const progress = Math.min(100, Math.round((completedSteps / totalSteps) * 100))
  const currentFlavorId = scoops[scoopIdx]
  const currentFlavor = FLAVORS.find((f) => f.id === currentFlavorId)
  const currentStage = SCOOP_STAGES[stageIdx]

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

      <span className="step-pill">STEP 5 · 스쿠핑 제조 중 ({orderId})</span>
      <h1 className="kiosk-title">아이스크림을 담고 있습니다</h1>
      <p className="kiosk-desc">
        <strong>
          {scoopIdx + 1} / {scoops.length} 스쿱 ({currentFlavor?.name})
        </strong>{' '}
        · {currentStage.label}
      </p>

      <div className="progress-block">
        <div className="progress-block__meta">
          <span className="mono">{currentStage.stage}</span>
          <span className="tabular">{progress}%</span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="scoop-progress-list">
        {scoops.map((flavorId, idx) => {
          const flavor = FLAVORS.find((f) => f.id === flavorId)
          const status =
            idx < scoopIdx ? '완료' : idx === scoopIdx ? '제조 중' : '대기'
          return (
            <div
              key={idx}
              className={`scoop-progress-item ${
                idx === scoopIdx ? 'scoop-progress-item--active' : ''
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
    </section>
  )
}
