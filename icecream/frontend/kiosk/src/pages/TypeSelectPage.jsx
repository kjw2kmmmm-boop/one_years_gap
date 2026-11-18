import { useState } from 'react'

export function TypeSelectPage({ measuredCup, maxScoops, onSelectCupIceCream, onBack }) {
  const [notice, setNotice] = useState('')

  return (
    <section className="kiosk-card">
      <div className="kiosk-card__top">
        <span className="step-pill">STEP 3 · 유형 선택</span>
        <span className="measure-badge">
          컵 측정 완료 · 높이 {measuredCup.heightZ}mm · 지름 {measuredCup.diameter}mm
        </span>
      </div>

      <h1 className="kiosk-title">아이스크림 유형을 선택해주세요</h1>
      <p className="kiosk-desc">
        측정된 컵 크기에 맞춰 아이스크림을 담아드립니다.
      </p>

      <div className="type-grid">
        <button
          type="button"
          className="type-option type-option--muted"
          onClick={() =>
            setNotice('소프트 아이스크림은 현재 준비 중입니다. 컵 아이스크림을 선택해 주세요.')
          }
        >
          <span className="type-option__tag">준비 중</span>
          <strong className="type-option__title">소프트 아이스크림</strong>
          <span className="type-option__sub">
            부드러운 소프트 콘/컵 디스펜싱
          </span>
        </button>

        <button
          type="button"
          className="type-option type-option--primary"
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

      {notice && <p className="inline-notice">{notice}</p>}

      <div className="kiosk-footer">
        <button type="button" className="ghost-btn" onClick={onBack}>
          컵 다시 측정하기
        </button>
      </div>
    </section>
  )
}
