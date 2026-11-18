export function StatusBanner({ feedback }) {
  return (
    <section
      className={`status-banner status-banner--${feedback.tone}`}
      aria-live="polite"
    >
      <div className="status-banner__content">
        <div className="status-banner__top">
          <span className="status-banner__label">{feedback.title}</span>
          {feedback.errorCode !== null && (
            <span className="status-banner__code">
              code {feedback.errorCode}
            </span>
          )}
        </div>
        <p className="status-banner__message">{feedback.message}</p>
      </div>
    </section>
  )
}
