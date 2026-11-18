import { useEffect, useState } from 'react'
import { MEASURE_STEPS } from '../services/kioskMockService'

export function MeasuringPage({ preset, onComplete }) {
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    setStepIndex(0)
    const timers = []

    MEASURE_STEPS.forEach((_, idx) => {
      if (idx > 0) {
        timers.push(setTimeout(() => setStepIndex(idx), idx * 650))
      }
    })

    const finishTimer = setTimeout(() => {
      onComplete({
        heightZ: preset.heightZ,
        diameter: preset.diameter,
      })
    }, MEASURE_STEPS.length * 650 + 350)

    return () => {
      timers.forEach(clearTimeout)
      clearTimeout(finishTimer)
    }
  }, [preset, onComplete])

  const current = MEASURE_STEPS[stepIndex]

  return (
    <section className="kiosk-card kiosk-card--center">
      <div className="pulse-ring" aria-hidden="true">
        <span className="pulse-ring__inner" />
      </div>

      <span className="step-pill">STEP 2 · 컵 규격 측정</span>
      <h1 className="kiosk-title">컵 크기를 측정하고 있습니다</h1>
      <p className="kiosk-desc">{current.label}</p>

      <div className="progress-block">
        <div className="progress-block__meta">
          <span className="mono">{current.phase}</span>
          <span className="tabular">{current.progress}%</span>
        </div>
        <div className="progress-track">
          <div
            className="progress-fill"
            style={{ width: `${current.progress}%` }}
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
    </section>
  )
}
