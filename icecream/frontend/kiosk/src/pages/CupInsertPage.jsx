import { CUP_PRESETS } from '../services/kioskMockService'

export function CupInsertPage({ selectedPresetId, onSelectPreset, onStartMeasure }) {
  return (
    <section className="kiosk-card kiosk-card--center">
      <div className="cup-illustration" aria-hidden="true">
        <svg width="112" height="112" viewBox="0 0 112 112" fill="none">
          <rect x="18" y="88" width="76" height="8" rx="4" fill="#DDD3C0" />
          <path
            d="M34 38H78L71 84C70.4 86.4 68.3 88 65.8 88H46.2C43.7 88 41.6 86.4 41 84L34 38Z"
            fill="#FFFDF8"
            stroke="#4C685B"
            strokeWidth="2.5"
          />
          <ellipse cx="56" cy="38" rx="22" ry="5.5" fill="#F1ECE1" stroke="#4C685B" strokeWidth="2.5" />
          <path d="M56 14V27" stroke="#4C685B" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M49 21L56 28L63 21" stroke="#4C685B" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <span className="step-pill">STEP 1 · 컵 준비</span>
      <h1 className="kiosk-title">컵을 넣어주세요</h1>
      <p className="kiosk-desc">
        컵을 측정판 중앙에 똑바로 올려놓은 뒤<br />
        아래 <strong>측정 시작</strong> 버튼을 눌러주세요.
      </p>

      <div className="preset-box">
        <span className="preset-box__label">목업 테스트용 가상 컵 크기 선택</span>
        <div className="preset-pills" role="group" aria-label="가상 컵 크기">
          {CUP_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className={`preset-pill ${
                selectedPresetId === preset.id ? 'preset-pill--active' : ''
              }`}
              onClick={() => onSelectPreset(preset.id)}
            >
              {preset.label} ({preset.heightZ}mm)
            </button>
          ))}
        </div>
      </div>

      <button
        type="button"
        className="primary-cta"
        onClick={onStartMeasure}
      >
        측정 시작
      </button>
    </section>
  )
}
