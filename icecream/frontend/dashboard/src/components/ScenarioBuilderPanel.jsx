import { useState } from 'react'
import { WAIT_ACTION } from '../hooks/useScenarioBuilder'

const STATUS_LABELS = {
  pending: '대기',
  running: '실행 중',
  success: '완료',
  error: '실패',
  stopped: '중단됨',
}

function parseDragPayload(event) {
  const raw = event.dataTransfer.getData('application/x-icecream-action')
  if (raw) {
    try {
      return JSON.parse(raw)
    } catch {
      return null
    }
  }
  const plainId = event.dataTransfer.getData('text/plain')
  if (plainId) {
    return { source: 'palette', actionId: plainId }
  }
  return null
}

export function ScenarioBuilderPanel({ actions, isGlobalBusy, scenario }) {
  const [presetName, setPresetName] = useState('')
  const [dropTargetIndex, setDropTargetIndex] = useState(null)
  const [isOverZone, setIsOverZone] = useState(false)

  const actionMap = new Map(actions.map((item) => [item.id, item]))
  const paletteItems = [...actions, WAIT_ACTION]
  const isLocked = scenario.isRunning || isGlobalBusy

  const handlePaletteDragStart = (event, item) => {
    const payload = {
      source: 'palette',
      actionId: item.id,
      param: item.defaultOption ?? (item.id === WAIT_ACTION.id ? 1.0 : undefined),
    }
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData('application/x-icecream-action', JSON.stringify(payload))
    event.dataTransfer.setData('text/plain', item.id)
  }

  const handleQueueDragStart = (event, index) => {
    const payload = { source: 'queue', fromIndex: index }
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('application/x-icecream-action', JSON.stringify(payload))
  }

  const handleDropAt = (event, targetIndex = null) => {
    event.preventDefault()
    event.stopPropagation()
    setIsOverZone(false)
    setDropTargetIndex(null)
    if (isLocked) return

    const payload = parseDragPayload(event)
    if (!payload) return

    if (payload.source === 'queue' && typeof payload.fromIndex === 'number') {
      const destination = targetIndex === null ? scenario.steps.length : targetIndex
      scenario.moveStep(payload.fromIndex, destination)
      return
    }

    if (payload.actionId) {
      scenario.addStep(payload.actionId, payload.param, targetIndex)
    }
  }

  const handleSavePreset = (event) => {
    event.preventDefault()
    if (scenario.savePreset(presetName)) {
      setPresetName('')
    }
  }

  return (
    <section className="scenario-panel" aria-label="간이 시나리오 빌더">
      <div className="manual-panel__header">
        <div>
          <h2 className="activity-panel__title">간이 시나리오 빌더 (드래그 앤 드롭)</h2>
          <p className="activity-panel__desc">
            왼쪽 행동 블록이나 하단 모션 카드를 오른쪽 시퀀스로 끌어다 놓고 순차 실행할 수 있습니다.
          </p>
        </div>

        <div className="order-filters">
          <button
            type="button"
            className="ghost-button"
            disabled={isLocked || scenario.steps.length === 0}
            onClick={scenario.clearSteps}
          >
            전체 비우기
          </button>
          {scenario.isRunning ? (
            <button
              type="button"
              className="stop-button"
              onClick={scenario.stopScenario}
            >
              시나리오 중단
            </button>
          ) : (
            <button
              type="button"
              className="script-run-button"
              disabled={isLocked || scenario.steps.length === 0}
              onClick={scenario.runScenario}
            >
              시나리오 실행 ({scenario.steps.length})
            </button>
          )}
        </div>
      </div>

      <div className="scenario-presets">
        <span className="manual-group__label">프리셋:</span>
        {scenario.presets.map((preset) => (
          <div key={preset.id} className="scenario-preset-chip">
            <button
              type="button"
              className="ghost-button scenario-preset-chip__btn"
              disabled={isLocked}
              onClick={() => scenario.loadPreset(preset)}
            >
              {preset.name} ({preset.steps.length})
            </button>
            {!preset.builtin && (
              <button
                type="button"
                className="scenario-preset-chip__del"
                disabled={isLocked}
                onClick={() => scenario.deletePreset(preset.id)}
                title="프리셋 삭제"
                aria-label={`${preset.name} 프리셋 삭제`}
              >
                ×
              </button>
            )}
          </div>
        ))}

        <form className="scenario-preset-form" onSubmit={handleSavePreset}>
          <input
            type="text"
            className="scenario-preset-input"
            placeholder="현재 시퀀스 저장명"
            value={presetName}
            disabled={isLocked || scenario.steps.length === 0}
            onChange={(e) => setPresetName(e.target.value)}
            maxLength={32}
          />
          <button
            type="submit"
            className="ghost-button"
            disabled={isLocked || !presetName.trim() || scenario.steps.length === 0}
          >
            저장
          </button>
        </form>
      </div>

      <div className="scenario-workspace">
        <div className="scenario-palette" aria-label="행동 팔레트">
          <div className="scenario-column__header">
            <span className="scenario-column__title">행동 블록</span>
            <span className="scenario-column__hint">드래그 또는 + 클릭</span>
          </div>
          <div className="scenario-palette__list">
            {paletteItems.map((item) => (
              <div
                key={item.id}
                className="scenario-chip"
                draggable={!isLocked}
                onDragStart={(e) => handlePaletteDragStart(e, item)}
              >
                <div className="scenario-chip__meta">
                  <span className="scenario-chip__grip" aria-hidden="true">
                    ⋮⋮
                  </span>
                  <div>
                    <div className="scenario-chip__title">{item.title}</div>
                    <div className="scenario-chip__id mono">{item.id}</div>
                  </div>
                </div>
                <button
                  type="button"
                  className="scenario-chip__add"
                  disabled={isLocked}
                  onClick={() =>
                    scenario.addStep(
                      item.id,
                      item.defaultOption ?? (item.id === WAIT_ACTION.id ? 1.0 : undefined),
                    )
                  }
                  title="시나리오 끝에 추가"
                  aria-label={`${item.title} 추가`}
                >
                  +
                </button>
              </div>
            ))}
          </div>
        </div>

        <div
          className={`scenario-queue ${isOverZone ? 'scenario-queue--over' : ''}`}
          aria-label="시나리오 실행 순서"
          onDragOver={(e) => {
            e.preventDefault()
            if (!isLocked) setIsOverZone(true)
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget)) {
              setIsOverZone(false)
              setDropTargetIndex(null)
            }
          }}
          onDrop={(e) => handleDropAt(e, null)}
        >
          <div className="scenario-column__header">
            <span className="scenario-column__title">
              실행 순서 ({scenario.steps.length}단계)
            </span>
            <span className="scenario-column__hint">
              위·아래 드래그로 순서 변경
            </span>
          </div>

          {scenario.steps.length === 0 ? (
            <div className="scenario-queue__empty">
              여기에 왼쪽 행동 블록이나 아래 모션 카드를 끌어다 놓으세요.
            </div>
          ) : (
            <ol className="scenario-queue__list">
              {scenario.steps.map((step, idx) => {
                const action =
                  step.actionId === WAIT_ACTION.id
                    ? WAIT_ACTION
                    : actionMap.get(step.actionId)
                const status = scenario.stepStatuses[step.uid]
                const isActive = scenario.runningIndex === idx

                return (
                  <li
                    key={step.uid}
                    className={`scenario-step ${
                      isActive ? 'scenario-step--running' : ''
                    } ${status ? `scenario-step--${status}` : ''} ${
                      dropTargetIndex === idx ? 'scenario-step--drop-before' : ''
                    }`}
                    draggable={!isLocked}
                    onDragStart={(e) => handleQueueDragStart(e, idx)}
                    onDragOver={(e) => {
                      e.preventDefault()
                      if (!isLocked) setDropTargetIndex(idx)
                    }}
                    onDrop={(e) => handleDropAt(e, idx)}
                  >
                    <div className="scenario-step__left">
                      <span className="scenario-chip__grip" aria-hidden="true">
                        ⋮⋮
                      </span>
                      <span className="scenario-step__index tabular">{idx + 1}</span>
                      <div className="scenario-step__info">
                        <span className="scenario-step__title">
                          {action?.title || step.actionId}
                        </span>
                        <span className="scenario-step__code mono">{step.actionId}</span>
                      </div>
                    </div>

                    <div className="scenario-step__controls">
                      {action?.options && (
                        <select
                          className="scenario-step__select"
                          value={step.param ?? action.defaultOption ?? ''}
                          disabled={isLocked}
                          onChange={(e) =>
                            scenario.updateStepParam(step.uid, e.target.value)
                          }
                          aria-label={`${idx + 1}단계 옵션`}
                        >
                          {action.options.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      )}

                      {step.actionId === WAIT_ACTION.id && (
                        <label className="scenario-wait-input-wrap">
                          <input
                            type="number"
                            min={0.1}
                            max={60}
                            step={0.5}
                            value={step.waitSec ?? 1.0}
                            disabled={isLocked}
                            onChange={(e) =>
                              scenario.updateStepWait(step.uid, e.target.value)
                            }
                            className="script-timeout-input tabular"
                            aria-label={`${idx + 1}단계 대기 초`}
                          />
                          <span>초</span>
                        </label>
                      )}

                      {status && (
                        <span className={`scenario-step__status scenario-step__status--${status}`}>
                          {STATUS_LABELS[status] || status}
                        </span>
                      )}

                      <button
                        type="button"
                        className="scenario-step__btn"
                        disabled={isLocked || idx === 0}
                        onClick={() => scenario.moveStep(idx, idx - 1)}
                        title="위로 이동"
                        aria-label={`${idx + 1}단계 위로`}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="scenario-step__btn"
                        disabled={isLocked || idx === scenario.steps.length - 1}
                        onClick={() => scenario.moveStep(idx, idx + 2)}
                        title="아래로 이동"
                        aria-label={`${idx + 1}단계 아래로`}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="scenario-step__btn scenario-step__btn--remove"
                        disabled={isLocked}
                        onClick={() => scenario.removeStep(step.uid)}
                        title="단계 삭제"
                        aria-label={`${idx + 1}단계 삭제`}
                      >
                        ×
                      </button>
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      </div>

      {scenario.statusFeedback && (
        <div
          className={`manual-feedback manual-feedback--${scenario.statusFeedback.tone}`}
          role="status"
        >
          {scenario.statusFeedback.message}
        </div>
      )}
    </section>
  )
}
