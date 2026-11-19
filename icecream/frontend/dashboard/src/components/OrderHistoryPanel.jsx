const STATUS_FILTERS = [
  { value: '', label: '전체' },
  { value: 'PENDING,IN_PROGRESS,SCOOPING,COMPLETING', label: '진행 중' },
  { value: 'COMPLETED', label: '완료' },
  { value: 'FAILED,CANCELLED', label: '실패' },
]

const STATUS_META = {
  PENDING: { label: '대기', badgeClass: 'badge--sand' },
  IN_PROGRESS: { label: '진행 중', badgeClass: 'badge--sand' },
  SCOOPING: { label: '제조 중', badgeClass: 'badge--sand' },
  COMPLETING: { label: '마무리', badgeClass: 'badge--sand' },
  COMPLETED: { label: '완료', badgeClass: 'badge--success' },
  FAILED: { label: '실패', badgeClass: 'badge--error' },
  CANCELLED: { label: '취소', badgeClass: 'badge--error' },
}

const FLAVOR_LABEL = {
  CHOCO: '초코',
  STRAWBERRY: '딸기',
  VANILLA: '바닐라',
}

function formatDateTime(isoString) {
  if (!isoString) return '-'
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function OrderHistoryPanel({
  orders,
  statusFilter,
  onChangeFilter,
  isLoading,
  error,
  onRefresh,
}) {
  return (
    <section className="activity-panel" aria-label="주문 내역">
      <div className="activity-panel__header">
        <div>
          <h2 className="activity-panel__title">주문 내역</h2>
          <p className="activity-panel__desc">
            키오스크 주문 및 order_manage 제조 진행 상태 (SQLite)
          </p>
        </div>

        <div className="order-panel__controls">
          <div className="order-filters" role="group" aria-label="주문 상태 필터">
            {STATUS_FILTERS.map((item) => (
              <button
                key={item.value || 'ALL'}
                type="button"
                className={`option-pill ${
                  statusFilter === item.value ? 'option-pill--active' : ''
                }`}
                onClick={() => onChangeFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <button type="button" className="ghost-button" onClick={onRefresh}>
            새로고침
          </button>
        </div>
      </div>

      {error && <div className="order-panel__error">{error}</div>}

      {isLoading && orders.length === 0 ? (
        <div className="activity-panel__empty">주문 내역을 불러오는 중입니다.</div>
      ) : orders.length === 0 ? (
        <div className="activity-panel__empty">표시할 주문 내역이 없습니다.</div>
      ) : (
        <ul className="activity-list">
          {orders.map((order) => {
            const meta = STATUS_META[order.order_status] ?? {
              label: order.order_status,
              badgeClass: 'badge--sand',
            }
            const scoopLabels = (order.scoops ?? []).map(
              (flavor) => FLAVOR_LABEL[flavor] || flavor,
            )
            const progress = Math.max(0, Math.min(100, Number(order.progress_percent ?? 0)))

            return (
              <li key={order.id ?? order.order_code} className="activity-item">
                <div className="order-item__top">
                  <div className="activity-item__meta">
                    <span className="order-item__code">{order.order_code}</span>
                    <span className={`badge ${meta.badgeClass}`}>{meta.label}</span>
                    <span className="activity-item__cmd">
                      {order.ice_cream_type === 'SOFT'
                        ? 'SOFT · 스파이럴'
                        : `${order.ice_cream_type} · ${order.scoop_count}스쿱`}
                    </span>
                  </div>
                  <span className="activity-item__time">
                    {formatDateTime(order.created_at)}
                  </span>
                </div>

                <div className="activity-item__detail">
                  <span className="activity-item__message">
                    {order.ice_cream_type === 'SOFT'
                      ? '소프트 아이스크림 스파이럴 제조'
                      : scoopLabels.length > 0
                        ? scoopLabels.join(' → ')
                        : '스쿱 정보 없음'}
                  </span>
                  <span className="activity-item__codes">
                    {order.cup_height_z != null
                      ? `컵 높이 ${Number(order.cup_height_z).toFixed(1)}mm`
                      : '컵 높이 미측정'}
                    {order.current_step ? ` · ${order.current_step}` : ''}
                    {` · ${progress.toFixed(0)}%`}
                  </span>
                </div>

                {order.order_status !== 'COMPLETED' && (
                  <div className="progress-track" aria-label="주문 제조 진행률">
                    <div
                      className="progress-fill"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                )}

                {order.error_message && (
                  <div className="order-item__error">
                    {order.error_code != null ? `[code ${order.error_code}] ` : ''}
                    {order.error_message}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
