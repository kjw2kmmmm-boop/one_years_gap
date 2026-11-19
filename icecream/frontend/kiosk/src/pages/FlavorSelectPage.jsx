import { useState } from 'react'
import { FLAVORS } from '../services/kioskMockService'

export function FlavorSelectPage({
  measuredCup,
  maxScoops,
  isSubmitting = false,
  submitError = '',
  onConfirm,
  onBack,
}) {
  const [scoops, setScoops] = useState([])

  const handleAddFlavor = (flavorId) => {
    if (scoops.length >= maxScoops) return
    setScoops((prev) => [...prev, flavorId])
  }

  const handleRemoveAt = (index) => {
    setScoops((prev) => prev.filter((_, idx) => idx !== index))
  }

  const handleFillAll = (flavorId) => {
    setScoops(Array.from({ length: maxScoops }, () => flavorId))
  }

  const chocoCount = scoops.filter((id) => id === 'CHOCO').length
  const strawberryCount = scoops.filter((id) => id === 'STRAWBERRY').length

  return (
    <section className="kiosk-card">
      <div className="kiosk-card__top">
        <span className="step-pill">STEP 4 · 맛 선택</span>
        <span className="measure-badge">
          컵 높이 {measuredCup.heightZ}mm · 총 {maxScoops}개 스쿱 가능
        </span>
      </div>

      <h1 className="kiosk-title">
        이 컵에는 총 <strong>{maxScoops}개</strong>의 스쿱이 들어갑니다
      </h1>
      <p className="kiosk-desc">
        원하시는 맛(초코 · 딸기)을 순서대로 선택해 주세요. ({scoops.length} / {maxScoops} 선택됨)
      </p>

      <div className="slot-row" aria-label="선택된 스쿱 목록">
        {Array.from({ length: maxScoops }, (_, idx) => {
          const flavorId = scoops[idx]
          const flavor = FLAVORS.find((f) => f.id === flavorId)
          return (
            <button
              key={idx}
              type="button"
              className={`scoop-slot ${flavor ? 'scoop-slot--filled' : ''}`}
              style={
                flavor
                  ? { backgroundColor: flavor.softBg, borderColor: flavor.swatch }
                  : undefined
              }
              disabled={!flavor}
              onClick={() => handleRemoveAt(idx)}
              title={flavor ? '클릭하여 제거' : '비어 있는 스쿱'}
            >
              <span className="scoop-slot__num">{idx + 1}번 스쿱</span>
              <span
                className="scoop-slot__dot"
                style={{ backgroundColor: flavor ? flavor.swatch : '#dfd7c8' }}
              />
              <span className="scoop-slot__name">
                {flavor ? flavor.name : '선택 대기'}
              </span>
            </button>
          )
        })}
      </div>

      <div className="flavor-grid">
        {FLAVORS.map((flavor) => (
          <div key={flavor.id} className="flavor-card">
            <button
              type="button"
              className="flavor-card__main"
              disabled={scoops.length >= maxScoops}
              onClick={() => handleAddFlavor(flavor.id)}
            >
              <span
                className="flavor-card__swatch"
                style={{ backgroundColor: flavor.swatch }}
              />
              <div className="flavor-card__text">
                <span className="flavor-card__eng">{flavor.engName}</span>
                <strong className="flavor-card__name">{flavor.name}</strong>
                <span className="flavor-card__desc">{flavor.desc}</span>
              </div>
              <span className="flavor-card__plus">+ 담기</span>
            </button>
            <button
              type="button"
              className="flavor-card__all"
              onClick={() => handleFillAll(flavor.id)}
            >
              {maxScoops}스쿱 모두 {flavor.name}로 채우기
            </button>
          </div>
        ))}
      </div>

      {submitError && (
        <p className="kiosk-desc" style={{ color: '#a95d47', marginTop: '12px' }}>
          {submitError}
        </p>
      )}

      <div className="kiosk-footer kiosk-footer--between">
        <div className="footer-left">
          <button type="button" className="ghost-btn" disabled={isSubmitting} onClick={onBack}>
            이전
          </button>
          {scoops.length > 0 && (
            <button
              type="button"
              className="ghost-btn"
              disabled={isSubmitting}
              onClick={() => setScoops([])}
            >
              선택 비우기
            </button>
          )}
        </div>

        <div className="footer-right">
          <span className="selection-summary">
            초코 {chocoCount} · 딸기 {strawberryCount}
          </span>
          <button
            type="button"
            className="primary-cta primary-cta--compact"
            disabled={scoops.length === 0 || isSubmitting}
            onClick={() => onConfirm(scoops)}
          >
            {isSubmitting ? '주문 전송 중...' : `확인 (${scoops.length}스쿱 제조 시작)`}
          </button>
        </div>
      </div>
    </section>
  )
}
