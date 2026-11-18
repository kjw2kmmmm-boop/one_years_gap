export function ActivityLog({ logs, onClear }) {
  return (
    <section className="activity-panel">
      <div className="activity-panel__header">
        <div>
          <h2 className="activity-panel__title">실행 이력</h2>
          <p className="activity-panel__desc">최근 대시보드 제어 명령과 ROS2 응답 기록</p>
        </div>
        {logs.length > 0 && (
          <button
            type="button"
            className="ghost-button"
            onClick={onClear}
          >
            기록 지우기
          </button>
        )}
      </div>

      {logs.length === 0 ? (
        <div className="activity-panel__empty">
          아직 실행된 모션 명령이 없습니다.
        </div>
      ) : (
        <ul className="activity-list">
          {logs.map((item) => (
            <li key={item.id} className="activity-item">
              <div className="activity-item__meta">
                <span className="activity-item__time">{item.timestamp}</span>
                <span
                  className={`badge ${
                    item.success ? 'badge--success' : 'badge--error'
                  }`}
                >
                  {item.success ? 'SUCCESS' : 'FAILED'}
                </span>
                <span className="activity-item__cmd">{item.command}</span>
              </div>
              <div className="activity-item__detail">
                <span className="activity-item__message">{item.message}</span>
                <span className="activity-item__codes">
                  {item.httpStatus ? `HTTP ${item.httpStatus}` : 'Network Error'}
                  {item.errorCode !== null ? ` · code ${item.errorCode}` : ''}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
