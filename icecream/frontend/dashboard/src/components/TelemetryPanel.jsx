const POSE_LABELS = ['X', 'Y', 'Z', 'Rx', 'Ry', 'Rz']

function formatNumber(value, digits = 2) {
  const num = Number(value ?? 0)
  return Number.isFinite(num) ? num.toFixed(digits) : '0.00'
}

export function TelemetryPanel({ telemetry, wsStatus }) {
  const tcpPose = telemetry.current_tcp_pose ?? [0, 0, 0, 0, 0, 0]
  const torques = telemetry.joint_torques ?? [0, 0, 0, 0, 0, 0]
  const isStreamLive = wsStatus === 'connected' && telemetry.connected

  return (
    <section className="telemetry-panel" aria-label="실시간 시스템 텔레메트리">
      <div className="telemetry-panel__header">
        <div>
          <h2 className="telemetry-panel__title">실시간 로봇 텔레메트리</h2>
          <p className="telemetry-panel__desc">
            ROS2 `/dashboard/telemetry` → WebSocket `/ws/telemetry`
          </p>
        </div>
        <span
          className={`telemetry-badge ${
            isStreamLive ? 'telemetry-badge--live' : 'telemetry-badge--idle'
          }`}
        >
          <span className="telemetry-badge__dot" aria-hidden="true" />
          {isStreamLive
            ? '실시간 수신 중'
            : wsStatus === 'connected'
              ? 'ROS 토픽 대기 중'
              : 'WS 재연결 중'}
        </span>
      </div>

      <div className="telemetry-summary">
        <div className="telemetry-stat">
          <span className="telemetry-stat__label">로봇 모드</span>
          <span
            className={`telemetry-stat__value ${
              telemetry.is_emergency_stopped ? 'text-clay' : ''
            }`}
          >
            {telemetry.robot_mode}
          </span>
        </div>

        <div className="telemetry-stat">
          <span className="telemetry-stat__label">시스템 상태</span>
          <span className="telemetry-stat__value">{telemetry.system_state}</span>
        </div>

        <div className="telemetry-stat">
          <span className="telemetry-stat__label">이동 상태</span>
          <span className="telemetry-stat__value">
            {telemetry.is_robot_moving ? 'MOVING' : 'STANDBY'}
          </span>
        </div>

        <div className="telemetry-stat">
          <span className="telemetry-stat__label">Z축 외력</span>
          <span className="telemetry-stat__value tabular">
            {formatNumber(telemetry.tool_force_z)} N
          </span>
        </div>

        <div className="telemetry-stat">
          <span className="telemetry-stat__label">최근 컵 높이</span>
          <span className="telemetry-stat__value tabular">
            {formatNumber(telemetry.latest_cup_height_z)} mm
          </span>
        </div>

        <div className="telemetry-stat">
          <span className="telemetry-stat__label">에러 / 컵 재고</span>
          <span
            className={`telemetry-stat__value tabular ${
              telemetry.active_error_code !== 0 || telemetry.cup_stock_warning
                ? 'text-clay'
                : ''
            }`}
          >
            err {telemetry.active_error_code} ·{' '}
            {telemetry.cup_stock_warning ? '컵 부족' : '정상'}
          </span>
        </div>
      </div>

      <div className="telemetry-details">
        <div className="telemetry-box">
          <div className="telemetry-box__title">현재 TCP 좌표 (mm / deg)</div>
          <div className="telemetry-axes">
            {POSE_LABELS.map((axis, idx) => (
              <div key={axis} className="telemetry-axis">
                <span className="telemetry-axis__label">{axis}</span>
                <span className="telemetry-axis__val tabular">
                  {formatNumber(tcpPose[idx])}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="telemetry-box">
          <div className="telemetry-box__title">관절 토크 (Nm)</div>
          <div className="telemetry-axes">
            {torques.map((val, idx) => (
              <div key={`J${idx + 1}`} className="telemetry-axis">
                <span className="telemetry-axis__label">J{idx + 1}</span>
                <span className="telemetry-axis__val tabular">
                  {formatNumber(val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="telemetry-order">
        <div className="telemetry-order__top">
          <span>
            현재 주문:{' '}
            <strong>{telemetry.current_order_id || '대기 중인 주문 없음'}</strong>
          </span>
          <span className="tabular">
            {formatNumber(telemetry.current_order_progress, 1)}%
          </span>
        </div>
        <div className="progress-track">
          <div
            className="progress-fill"
            style={{
              width: `${Math.min(100, Math.max(0, telemetry.current_order_progress || 0))}%`,
            }}
          />
        </div>
      </div>
    </section>
  )
}
