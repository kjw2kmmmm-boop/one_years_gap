const TASK_AXES = [
  { label: 'X', unit: 'mm', isRot: false },
  { label: 'Y', unit: 'mm', isRot: false },
  { label: 'Z', unit: 'mm', isRot: false },
  { label: 'Rx', unit: '°', isRot: true },
  { label: 'Ry', unit: '°', isRot: true },
  { label: 'Rz', unit: '°', isRot: true },
]

const JOINT_AXES = [
  { label: 'J1', unit: '°', isRot: true },
  { label: 'J2', unit: '°', isRot: true },
  { label: 'J3', unit: '°', isRot: true },
  { label: 'J4', unit: '°', isRot: true },
  { label: 'J5', unit: '°', isRot: true },
  { label: 'J6', unit: '°', isRot: true },
]

const MM_STEPS = [1, 5, 10, 30]
const DEG_STEPS = [1, 5, 15]
const OP_SPEEDS = [20, 50, 80, 100]

export function ManualControlPanel({ telemetry, manual }) {
  const isJoint = manual.space === 'joint'
  const axes = isJoint ? JOINT_AXES : TASK_AXES
  const liveValues = isJoint
    ? (telemetry.current_joint_angles ?? [0, 0, 0, 0, 0, 0])
    : (telemetry.current_tcp_pose ?? [0, 0, 0, 0, 0, 0])

  const copyCoords = async (kind) => {
    const arr =
      kind === 'joint'
        ? (telemetry.current_joint_angles ?? [0, 0, 0, 0, 0, 0])
        : (telemetry.current_tcp_pose ?? [0, 0, 0, 0, 0, 0])
    const formatted = `[${arr.map((v) => Number(v ?? 0).toFixed(2)).join(', ')}]`
    try {
      await navigator.clipboard.writeText(formatted)
      manual.setFeedback({
        tone: 'success',
        message: `${kind === 'joint' ? 'Joint' : 'TCP'} 좌표 복사됨: ${formatted}`,
      })
    } catch {
      manual.setFeedback({
        tone: 'neutral',
        message: `좌표: ${formatted}`,
      })
    }
  }

  return (
    <section className="manual-panel" aria-label="수동 로봇 조작">
      <div className="manual-panel__header">
        <div>
          <h2 className="activity-panel__title">수동 로봇 조작 (Jog &amp; Step)</h2>
          <p className="activity-panel__desc">
            스텝 증분 이동 · 누르는 동안 연속 조그(Hold) · 즉시 정지(STOP)
          </p>
        </div>

        <button
          type="button"
          className="stop-button"
          onClick={manual.triggerStop}
        >
          STOP 정지
        </button>
      </div>

      <div className="manual-toolbar">
        <div className="manual-group">
          <span className="manual-group__label">조작 방식</span>
          <div className="order-filters">
            <button
              type="button"
              className={`option-pill ${manual.controlMode === 'step' ? 'option-pill--active' : ''}`}
              onClick={() => manual.setControlMode('step')}
            >
              스텝 이동 (클릭)
            </button>
            <button
              type="button"
              className={`option-pill ${manual.controlMode === 'jog' ? 'option-pill--active' : ''}`}
              onClick={() => manual.setControlMode('jog')}
            >
              연속 조그 (Hold)
            </button>
          </div>
        </div>

        <div className="manual-group">
          <span className="manual-group__label">좌표계</span>
          <div className="order-filters">
            <button
              type="button"
              className={`option-pill ${manual.space === 'task_base' ? 'option-pill--active' : ''}`}
              onClick={() => manual.setSpace('task_base')}
            >
              Task (BASE)
            </button>
            <button
              type="button"
              className={`option-pill ${manual.space === 'task_tool' ? 'option-pill--active' : ''}`}
              onClick={() => manual.setSpace('task_tool')}
            >
              Task (TOOL)
            </button>
            <button
              type="button"
              className={`option-pill ${manual.space === 'joint' ? 'option-pill--active' : ''}`}
              onClick={() => manual.setSpace('joint')}
            >
              Joint (J1~J6)
            </button>
          </div>
        </div>
      </div>

      <div className="manual-toolbar">
        {manual.controlMode === 'step' && (
          <div className="manual-group">
            <span className="manual-group__label">
              {isJoint ? '스텝 각도 (°)' : '스텝 거리 (mm) / 회전 (°)'}
            </span>
            <div className="order-filters">
              {!isJoint &&
                MM_STEPS.map((mm) => (
                  <button
                    key={`mm-${mm}`}
                    type="button"
                    className={`option-pill ${manual.stepSizeMm === mm ? 'option-pill--active' : ''}`}
                    onClick={() => manual.setStepSizeMm(mm)}
                  >
                    {mm}mm
                  </button>
                ))}
              {DEG_STEPS.map((deg) => (
                <button
                  key={`deg-${deg}`}
                  type="button"
                  className={`option-pill ${manual.stepSizeDeg === deg ? 'option-pill--active' : ''}`}
                  onClick={() => manual.setStepSizeDeg(deg)}
                >
                  {deg}°
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="manual-group">
          <span className="manual-group__label">
            수동 속도: <strong className="tabular">{manual.speedPct}%</strong> (최대 50%)
          </span>
          <input
            type="range"
            min="5"
            max="50"
            step="5"
            value={manual.speedPct}
            onChange={(e) => manual.setSpeedPct(Number(e.target.value))}
            aria-label="수동 이동 속도"
          />
        </div>
      </div>

      <div className="manual-axes-grid">
        {axes.map((axis, idx) => {
          const val = Number(liveValues[idx] ?? 0).toFixed(2)
          const minusKey = `${manual.space}-${idx}-minus`
          const plusKey = `${manual.space}-${idx}-plus`

          return (
            <div key={axis.label} className="manual-axis-card">
              <div className="manual-axis-card__top">
                <span className="manual-axis-card__name">{axis.label}</span>
                <span className="manual-axis-card__val tabular">
                  {val} {axis.unit}
                </span>
              </div>
              <div className="manual-axis-card__btns">
                {manual.controlMode === 'step' ? (
                  <>
                    <button
                      type="button"
                      className="jog-btn"
                      disabled={manual.isBusy}
                      onClick={() => manual.triggerStep(idx, -1)}
                    >
                      - {axis.isRot ? `${manual.stepSizeDeg}°` : `${manual.stepSizeMm}mm`}
                    </button>
                    <button
                      type="button"
                      className="jog-btn"
                      disabled={manual.isBusy}
                      onClick={() => manual.triggerStep(idx, 1)}
                    >
                      + {axis.isRot ? `${manual.stepSizeDeg}°` : `${manual.stepSizeMm}mm`}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className={`jog-btn ${manual.activeJogKey === minusKey ? 'jog-btn--active' : ''}`}
                      onPointerDown={() => manual.startJog(idx, -1, minusKey)}
                      onPointerUp={manual.stopJog}
                      onPointerLeave={manual.stopJog}
                      onPointerCancel={manual.stopJog}
                    >
                      ◀ - {axis.label}
                    </button>
                    <button
                      type="button"
                      className={`jog-btn ${manual.activeJogKey === plusKey ? 'jog-btn--active' : ''}`}
                      onPointerDown={() => manual.startJog(idx, 1, plusKey)}
                      onPointerUp={manual.stopJog}
                      onPointerLeave={manual.stopJog}
                      onPointerCancel={manual.stopJog}
                    >
                      + {axis.label} ▶
                    </button>
                  </>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="manual-footer">
        <div className="order-filters">
          <button
            type="button"
            className="ghost-button"
            onClick={() => manual.changeRobotMode(0)}
          >
            MANUAL 모드
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={() => manual.changeRobotMode(1)}
          >
            AUTONOMOUS 모드
          </button>
          {OP_SPEEDS.map((sp) => (
            <button
              key={`op-${sp}`}
              type="button"
              className="ghost-button"
              onClick={() => manual.changeOperationSpeed(sp)}
            >
              전체속도 {sp}%
            </button>
          ))}
        </div>

        <div className="order-filters">
          <button type="button" className="ghost-button" onClick={() => copyCoords('tcp')}>
            현재 TCP 복사
          </button>
          <button type="button" className="ghost-button" onClick={() => copyCoords('joint')}>
            현재 Joint 복사
          </button>
        </div>
      </div>

      {manual.feedback && (
        <div
          className={`manual-feedback manual-feedback--${manual.feedback.tone}`}
        >
          {manual.feedback.message}
        </div>
      )}
    </section>
  )
}
