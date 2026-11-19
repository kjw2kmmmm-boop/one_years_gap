export function TypeSelectPage({
  measuredCup,
  maxScoops,
  isSubmitting = false,
  submitError = '',
  onSelectSoftIceCream,
  onSelectCupIceCream,
  onBack,
}) {
  return (
    <section className="kiosk-card">
      <div className="kiosk-card__top">
        <span className="step-pill">STEP 3 · 유형 선택</span>
        <span className="measure-badge">
          컵 규격 · 높이 {measuredCup.heightZ}mm · 지름 {measuredCup.diameter}mm
        </span>
      </div>

      <h1 className="kiosk-title">아이스크림 유형을 선택해주세요</h1>
      <p className="kiosk-desc">
        원하시는 아이스크림 유형을 선택하면 제조를 진행합니다.
      </p>

      <div className="type-grid">
        <button
          type="button"
          className="type-option type-option--primary"
          disabled={isSubmitting}
          onClick={onSelectSoftIceCream}
        >
          <span className="type-option__tag type-option__tag--active">
            {isSubmitting ? '주문 전송 중...' : '스파이럴 바로 시작'}
          </span>
          <strong className="type-option__title">소프트 아이스크림</strong>
          <span className="type-option__sub">
            컵 홀드 → 중간 이동 → 스파이럴 제조 → 놓기 · HOME 복귀
          </span>
        </button>

        <button
          type="button"
          className="type-option type-option--primary"
          disabled={isSubmitting}
          onClick={onSelectCupIceCream}
        >
          <span className="type-option__tag type-option__tag--active">
            최대 {maxScoops}스쿱 가능
          </span>
          <strong className="type-option__title">컵 아이스크림</strong>
          <span className="type-option__sub">
            원하는 맛을 스쿱으로 골라 담기 (초코 · 딸기)
          </span>
        </button>
      </div>

      {submitError && (
        <p className="inline-notice" style={{ color: '#a95d47' }}>
          {submitError}
        </p>
      )}

      <div className="kiosk-footer">
        <button
          type="button"
          className="ghost-btn"
          disabled={isSubmitting}
          onClick={onBack}
        >
          컵 다시 측정하기
        </button>
      </div>
    </section>
  )
}
