export function ScriptRunnerPanel({ runner }) {
  const isLocked = runner.isRunning || runner.isBlockedByOther
  const lockOwnerLabel =
    runner.remoteClientIp &&
    runner.remoteClientIp !== '127.0.0.1' &&
    runner.remoteClientIp !== '::1'
      ? ` (${runner.remoteClientIp})`
      : ''

  const handleKeyDown = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault()
      const target = e.target
      const start = target.selectionStart
      const end = target.selectionEnd
      const next =
        runner.code.slice(0, start) + '    ' + runner.code.slice(end)
      runner.setCode(next)
      requestAnimationFrame(() => {
        target.selectionStart = target.selectionEnd = start + 4
      })
    }
  }

  return (
    <section className="script-panel" aria-label="원격 파이썬 실행기">
      <div className="manual-panel__header">
        <div>
          <h2 className="activity-panel__title">원격 파이썬 코드 실행 (팀원 테스트용)</h2>
          <p className="activity-panel__desc">
            코드를 붙여넣고 실행하면 호스트 PC의 ROS2(ws_dsr) 환경에서 직접 실행됩니다.
          </p>
        </div>

        <div className="order-filters">
          <button
            type="button"
            className="ghost-button"
            disabled={isLocked}
            onClick={runner.resetTemplate}
          >
            기본 템플릿
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={runner.clearOutput}
          >
            로그 지우기
          </button>
          <button
            type="button"
            className="stop-button"
            onClick={runner.stopScript}
          >
            중단 + 로봇 정지
          </button>
          <button
            type="button"
            className="script-run-button"
            disabled={isLocked || !runner.code.trim()}
            onClick={runner.runScript}
          >
            {runner.isRunning
              ? '실행 중...'
              : runner.isBlockedByOther
                ? '다른 사용자 실행 중'
                : '파이썬 실행'}
          </button>
        </div>
      </div>

      {runner.isBlockedByOther && (
        <div className="manual-feedback manual-feedback--error" role="status">
          다른 사용자가 파이썬 스크립트를 실행 중입니다{lockOwnerLabel}. 완료될 때까지 이 화면에서는 코드 수정과 실행이 차단됩니다.
        </div>
      )}

      <div className="manual-toolbar">
        <label className="script-option">
          <input
            type="checkbox"
            checked={runner.autoEnter}
            disabled={isLocked}
            onChange={(e) => runner.setAutoEnter(e.target.checked)}
          />
          <span>코드 내 input() 자동 Enter 통과</span>
        </label>

        <label className="script-option">
          <span>타임아웃(초):</span>
          <input
            type="number"
            min={5}
            max={300}
            value={runner.timeoutSec}
            disabled={isLocked}
            onChange={(e) => runner.setTimeoutSec(Number(e.target.value) || 120)}
            className="script-timeout-input tabular"
          />
        </label>
      </div>

      <textarea
        className="script-editor"
        value={runner.code}
        onChange={(e) => runner.setCode(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isLocked}
        spellCheck={false}
        rows={14}
        aria-label="파이썬 코드 입력"
      />

      {runner.status && (
        <div
          className={`manual-feedback manual-feedback--${
            runner.status.tone === 'running' ? 'neutral' : runner.status.tone
          }`}
        >
          {runner.status.message}
        </div>
      )}

      <div className="script-console" aria-live="polite">
        {runner.outputLines.length === 0 ? (
          <span className="script-console__empty">
            실행 출력(stdout / stderr)이 여기에 실시간 표시됩니다.
          </span>
        ) : (
          runner.outputLines.map((item) => (
            <div
              key={item.id}
              className={`script-console__line ${
                item.stream === 'stderr' ? 'script-console__line--err' : ''
              }`}
            >
              {item.line}
            </div>
          ))
        )}
      </div>
    </section>
  )
}
