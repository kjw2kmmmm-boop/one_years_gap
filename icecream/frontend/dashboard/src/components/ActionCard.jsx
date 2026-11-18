import { useState } from 'react'

export function ActionCard({ action, isRunning, isDisabled, onExecute }) {
  const [selectedOption, setSelectedOption] = useState(action.defaultOption ?? '')
  const activeOption = action.options?.find((opt) => opt.value === selectedOption)
  const specText = activeOption?.spec ?? action.spec

  return (
    <article className={`action-card ${isRunning ? 'action-card--running' : ''}`}>
      <div className="action-card__header">
        <span className="action-card__endpoint">{action.endpoint}</span>
        <span className="action-card__command">{action.id}</span>
      </div>

      <div className="action-card__body">
        <h2 className="action-card__title">{action.title}</h2>
        <p className="action-card__subtitle">{action.subtitle}</p>
        {action.options && (
          <div className="option-pills" role="group" aria-label="옵션 선택">
            {action.options.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`option-pill ${
                  selectedOption === opt.value ? 'option-pill--active' : ''
                }`}
                disabled={isDisabled}
                onClick={() => setSelectedOption(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
        <p className="action-card__spec">{specText}</p>
      </div>

      <button
        type="button"
        className="action-card__button"
        disabled={isDisabled}
        onClick={() => onExecute(action, action.options ? selectedOption : undefined)}
      >
        {isRunning ? (
          <>
            <span className="spinner" aria-hidden="true" />
            <span>동작 실행 중…</span>
          </>
        ) : (
          <span>실행하기</span>
        )}
      </button>
    </article>
  )
}
