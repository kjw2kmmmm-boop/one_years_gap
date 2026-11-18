import { FLAVORS } from '../services/kioskMockService'

export function CompletePage({ orderId, measuredCup, scoops, onReset }) {
  const summary = FLAVORS.map((flavor) => ({
    ...flavor,
    count: scoops.filter((id) => id === flavor.id).length,
  })).filter((item) => item.count > 0)

  return (
    <section className="kiosk-card kiosk-card--center">
      <div className="complete-check" aria-hidden="true">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
          <path
            d="M5 13L9 17L19 7"
            stroke="#FFFDF8"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <span className="step-pill">STEP 6 · 제조 완료</span>
      <h1 className="kiosk-title">아이스크림이 완성되었습니다</h1>
      <p className="kiosk-desc">
        픽업 존에서 완성된 컵 아이스크림을 받아가세요.
      </p>

      <div className="receipt-box">
        <div className="receipt-row">
          <span>주문 번호</span>
          <strong className="mono">{orderId}</strong>
        </div>
        <div className="receipt-row">
          <span>유형</span>
          <strong>컵 아이스크림 ({scoops.length}스쿱)</strong>
        </div>
        <div className="receipt-row">
          <span>측정 컵 높이</span>
          <strong className="tabular">{measuredCup.heightZ} mm</strong>
        </div>
        <div className="receipt-row">
          <span>맛 구성</span>
          <strong>
            {summary.map((item) => `${item.name} ${item.count}`).join(' · ')}
          </strong>
        </div>
      </div>

      <button type="button" className="primary-cta" onClick={onReset}>
        처음 화면으로
      </button>
    </section>
  )
}
