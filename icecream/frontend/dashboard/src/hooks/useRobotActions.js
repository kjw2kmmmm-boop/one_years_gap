import { useCallback, useEffect, useState } from 'react'
import {
  calibrateCupDiameter,
  calibrateCupZ,
  checkBackendHealth,
  clearActionLogs,
  fetchActionLogs,
  gripAndLift,
  gripperCup,
  gripperGrab,
  gripperRelease,
  moveCupHold,
  moveCupMiddle,
  moveCupSprial,
  moveCupZ,
  moveRobotHome,
  moveRobotToScoop,
  moveToFlavor,
  moveToPlate,
  pushCupCorner,
} from '../services/dashboardApi'

export const FLAVOR_OPTIONS = [
  {
    value: 'CHOCO',
    label: '초코 (CHOCO)',
    spec: 'TCP = [574.76, 88.09, 344.64] · vel 80',
  },
  {
    value: 'STRAWBERRY',
    label: '딸기 (STRAWBERRY)',
    spec: 'TCP = [573.59, -77.70, 344.64] · vel 80',
  },
]

export const ROBOT_ACTIONS = [
  {
    id: 'MOVE_HOME',
    title: 'HOME 위치 이동',
    subtitle: '관절 홈 자세 복귀 및 그리퍼 열기',
    endpoint: 'POST /home',
    spec: 'J = [0, 0, 90, 0, 90, 0] · vel 70 · acc 70',
    run: moveRobotHome,
  },
  {
    id: 'MOVE_TO_SCOOP',
    title: '스쿠프 위치 이동',
    subtitle: '현재 높이 유지 수평 이동 후 수직 하강',
    endpoint: 'POST /move-to-scoop',
    spec: 'TCP = [426.52, 222.05, 344.64] · vel 80',
    run: moveRobotToScoop,
  },
  {
    id: 'MOVE_CUP_Z',
    title: '컵 측정 위치 이동',
    subtitle: '컵 Z 높이 측정 기준 좌표로 직선 이동',
    endpoint: 'POST /move-cup-z',
    spec: 'TCP = [338.57, -170.40, 556.32] · vel 80',
    run: moveCupZ,
  },
  {
    id: 'MOVE_CUP_HOLD',
    title: '컵 홀드 위치 이동',
    subtitle: '컵 홀드 기준 좌표로 X→Y→Z 순 이동',
    endpoint: 'POST /move-cup-hold',
    spec: 'TCP = [354.19, -143.42, 370.58] · vel 80',
    run: moveCupHold,
  },
  {
    id: 'MOVE_CUP_MIDDLE',
    title: '컵 중간 위치 이동',
    subtitle: '그립한 컵을 spiral 시작 위치로 상대 이동 후 Tool Ry +10°',
    endpoint: 'POST /move-cup-middle',
    spec: 'rel [+70.0, +70.0, +50.0] · TOOL Ry +10° · vel 30',
    run: moveCupMiddle,
  },
  {
    id: 'MOVE_CUP_SPRIAL',
    title: '컵 스파이럴 모션',
    subtitle: '현재 위치에서 나선형 하강 스파이럴(movesx) 실행',
    endpoint: 'POST /move-cup-sprial',
    spec: 'turns 5 · R 20mm · H 60mm · time 10.0s',
    run: moveCupSprial,
  },
  {
    id: 'MOVE_TO_PLATE',
    title: '측정판 위치 이동',
    subtitle: '측정판 손잡이 좌표로 직선 이동',
    endpoint: 'POST /move-to-plate',
    spec: 'TCP = [578.45, -222.64, 284.72] · vel 80',
    run: moveToPlate,
  },
  {
    id: 'MOVE_TO_FLAVOR',
    title: '아이스크림 맛 위치 이동',
    subtitle: '선택한 맛 통 상단 위치로 직선 이동',
    endpoint: 'POST /move-to-flavor',
    options: FLAVOR_OPTIONS,
    defaultOption: 'CHOCO',
    run: (flavor) => moveToFlavor(flavor),
  },
  {
    id: 'GRIP_AND_LIFT',
    title: '그리퍼 닫기 및 상승',
    subtitle: '그리퍼 파지 신호 후 Z축 15cm 상대 상승',
    endpoint: 'POST /grip-and-lift',
    spec: 'DO1 ON/OFF · rel Z +150mm · vel 80',
    run: gripAndLift,
  },
  {
    id: 'GRIPPER_RELEASE',
    title: '그리퍼 열기',
    subtitle: 'DO1 OFF 후 DO2 2.5초 펄스 출력',
    endpoint: 'POST /gripper-release',
    spec: 'DO1=0 · DO2=1 (2.5s) → 0',
    run: gripperRelease,
  },
  {
    id: 'GRIPPER_GRAB',
    title: '그리퍼 닫기',
    subtitle: 'DO2 OFF 후 DO1 2.5초 펄스 출력',
    endpoint: 'POST /gripper-grab',
    spec: 'DO2=0 · DO1=1 (2.5s) → 0',
    run: gripperGrab,
  },
  {
    id: 'GRIPPER_CUP',
    title: '컵 그리퍼 닫기',
    subtitle: 'DO1/DO2 OFF 후 DO3 2.5초 펄스 출력',
    endpoint: 'POST /gripper-cup',
    spec: 'DO1,2=0 · DO3=1 (2.5s) → 0',
    run: gripperCup,
  },
  {
    id: 'CALIBRATE_CUP_Z',
    title: '컵 높이 측정 (Z)',
    subtitle: '하강 접촉 감지로 컵 높이 측정 후 원위치 복귀',
    endpoint: 'POST /calibrate-cup-z',
    spec: 'vel 20 → 접촉(≥2N) → offset -238mm',
    run: calibrateCupZ,
  },
  {
    id: 'PUSH_CUP_CORNER',
    title: '컵 코너 밀착',
    subtitle: '외력 감지로 컵을 코너 벽까지 스무스하게 밀착',
    endpoint: 'POST /push-cup-corner',
    spec: 'LOW_Z 210mm · vel 15 → 벽 접촉(≥1.8N) → 45mm 후퇴',
    run: pushCupCorner,
  },
  {
    id: 'CALIBRATE_CUP_DIAMETER',
    title: '컵 지름 측정',
    subtitle: '측면 접촉 감지로 컵 반지름·지름(mm) 실측',
    endpoint: 'POST /calibrate-cup-diameter',
    spec: '측정높이 Z 연동(미측정 시 335mm) · vel 4 → 측면 접촉(≥1.5N)',
    run: calibrateCupDiameter,
  },
]

function formatTime(date) {
  return date.toLocaleTimeString('ko-KR', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function mapActionLogRow(row) {
  const executedDate = row.executed_at ? new Date(row.executed_at) : new Date()
  return {
    id: String(row.id),
    timestamp: formatTime(executedDate),
    command: row.target ? `${row.command}:${row.target}` : row.command,
    title: row.command,
    success: row.status === 'SUCCESS',
    errorCode: row.error_code ?? null,
    message: row.message || (row.status === 'RUNNING' ? '실행 중' : ''),
    httpStatus: row.http_status ?? null,
  }
}

export function useRobotActions() {
  const [backendStatus, setBackendStatus] = useState('checking')
  const [activeActionId, setActiveActionId] = useState(null)
  const [lastFeedback, setLastFeedback] = useState({
    tone: 'neutral',
    title: '대기 중',
    message: '제어할 모션을 선택하면 ROS2 ExecuteTask 서비스로 전달됩니다.',
    errorCode: null,
  })
  const [logs, setLogs] = useState([])

  const refreshHealth = useCallback(async () => {
    try {
      await checkBackendHealth()
      setBackendStatus('connected')
    } catch {
      setBackendStatus('disconnected')
    }
  }, [])

  useEffect(() => {
    refreshHealth()
    fetchActionLogs(12)
      .then((rows) => {
        if (Array.isArray(rows) && rows.length > 0) {
          setLogs(rows.map(mapActionLogRow))
        }
      })
      .catch(() => {})
    const timer = setInterval(refreshHealth, 10000)
    return () => clearInterval(timer)
  }, [refreshHealth])

  const executeAction = useCallback(
    async (action, param) => {
      if (activeActionId) return

      const label = param ? `${action.title} (${param})` : action.title
      setActiveActionId(action.id)
      setLastFeedback({
        tone: 'running',
        title: `${label} 실행 중`,
        message: `${action.endpoint} 요청을 전송하고 로봇 완료 응답을 기다리는 중입니다.`,
        errorCode: null,
      })

      try {
        const result = await action.run(param)
        const entry = {
          id: `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
          timestamp: formatTime(new Date()),
          command: param ? `${action.id}:${param}` : action.id,
          title: label,
          success: Boolean(result?.success),
          errorCode: result?.error_code ?? 0,
          message: result?.message || '완료되었습니다.',
          httpStatus: 200,
        }

        setBackendStatus('connected')
        setLastFeedback({
          tone: 'success',
          title: `${label} 완료`,
          message: entry.message,
          errorCode: entry.errorCode,
        })
        setLogs((prev) => [entry, ...prev].slice(0, 12))
      } catch (err) {
        const entry = {
          id: `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
          timestamp: formatTime(new Date()),
          command: param ? `${action.id}:${param}` : action.id,
          title: label,
          success: false,
          errorCode: err.errorCode ?? null,
          message: err.message || '요청 처리 중 오류가 발생했습니다.',
          httpStatus: err.status ?? null,
        }

        if (!err.status) {
          setBackendStatus('disconnected')
        }
        setLastFeedback({
          tone: 'error',
          title: `${label} 실패`,
          message: entry.message,
          errorCode: entry.errorCode,
        })
        setLogs((prev) => [entry, ...prev].slice(0, 12))
      } finally {
        setActiveActionId(null)
      }
    },
    [activeActionId],
  )

  const clearLogs = useCallback(() => {
    setLogs([])
    clearActionLogs().catch(() => {})
  }, [])

  return {
    actions: ROBOT_ACTIONS,
    backendStatus,
    activeActionId,
    isBusy: Boolean(activeActionId),
    lastFeedback,
    logs,
    executeAction,
    refreshHealth,
    clearLogs,
  }
}
