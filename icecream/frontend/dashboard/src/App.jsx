import { ActionCard } from './components/ActionCard'
import { ActivityLog } from './components/ActivityLog'
import { ManualControlPanel } from './components/ManualControlPanel'
import { OrderHistoryPanel } from './components/OrderHistoryPanel'
import { ScenarioBuilderPanel } from './components/ScenarioBuilderPanel'
import { ScriptRunnerPanel } from './components/ScriptRunnerPanel'
import { StatusBanner } from './components/StatusBanner'
import { TelemetryPanel } from './components/TelemetryPanel'
import { useManualControl } from './hooks/useManualControl'
import { useOrders } from './hooks/useOrders'
import { useRobotActions } from './hooks/useRobotActions'
import { useScenarioBuilder } from './hooks/useScenarioBuilder'
import { useScriptRunner } from './hooks/useScriptRunner'
import { useTelemetry } from './hooks/useTelemetry'

const HEALTH_LABEL = {
  checking: '연결 확인 중',
  connected: '백엔드 연결됨',
  disconnected: '백엔드 연결 안 됨',
}

export default function App() {
  const {
    actions,
    backendStatus,
    activeActionId,
    isBusy,
    lastFeedback,
    logs,
    executeAction,
    refreshHealth,
    clearLogs,
  } = useRobotActions()
  const { telemetry, wsStatus } = useTelemetry()
  const manual = useManualControl()
  const scriptRunner = useScriptRunner()
  const scenario = useScenarioBuilder({
    actions,
    executeAction,
    isGlobalBusy: isBusy,
  })
  const isAnyActionBusy = isBusy || scenario.isRunning
  const {
    orders,
    statusFilter,
    setStatusFilter,
    isLoading: isOrdersLoading,
    error: ordersError,
    refreshOrders,
  } = useOrders({
    refreshKey: `${telemetry.current_order_id}:${telemetry.system_state}`,
  })

  const handleExecuteAction = (action, param) => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
    executeAction(action, param)
  }

  return (
    <div className="page-shell">
      <main className="dashboard-container">
        <header className="dashboard-header">
          <div>
            <p className="dashboard-eyebrow">DOOSAN M0609 · ICECREAM COBOT</p>
            <h1 className="dashboard-title">로봇 제어 대시보드</h1>
            <p className="dashboard-subtitle">
              백엔드 API와 ROS2 텔레메트리를 통해 로봇 상태 모니터링 및 수동 제어를 수행합니다.
            </p>
          </div>

          <button
            type="button"
            className={`connection-pill connection-pill--${backendStatus}`}
            onClick={refreshHealth}
            title="백엔드 연결 상태 다시 확인"
          >
            <span className="connection-pill__dot" aria-hidden="true" />
            <span>{HEALTH_LABEL[backendStatus]}</span>
          </button>
        </header>

        <StatusBanner feedback={lastFeedback} />

        <TelemetryPanel telemetry={telemetry} wsStatus={wsStatus} />

        <ManualControlPanel telemetry={telemetry} manual={manual} />

        <ScriptRunnerPanel runner={scriptRunner} />

        <ScenarioBuilderPanel
          actions={actions}
          isGlobalBusy={isAnyActionBusy}
          scenario={scenario}
        />

        <section className="actions-grid" aria-label="로봇 모션 제어">
          {actions.map((action) => (
            <ActionCard
              key={action.id}
              action={action}
              isRunning={activeActionId === action.id}
              isDisabled={isAnyActionBusy}
              onExecute={handleExecuteAction}
            />
          ))}
        </section>

        <OrderHistoryPanel
          orders={orders}
          statusFilter={statusFilter}
          onChangeFilter={setStatusFilter}
          isLoading={isOrdersLoading}
          error={ordersError}
          onRefresh={refreshOrders}
        />

        <ActivityLog logs={logs} onClear={clearLogs} />
      </main>
    </div>
  )
}
