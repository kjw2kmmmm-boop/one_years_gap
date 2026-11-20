import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_STEPS_KEY = 'icecream.dashboard.scenario.v1'
const STORAGE_PRESETS_KEY = 'icecream.dashboard.scenarioPresets.v1'

export const WAIT_ACTION = {
  id: 'WAIT',
  title: '대기 (Wait)',
  subtitle: '다음 동작 전 지정 시간(초)만큼 일시 대기',
  endpoint: 'CLIENT WAIT',
}

export const BUILT_IN_SCENARIO_PRESETS = [
  {
    id: 'builtin-soft-full',
    name: '소프트 풀코스',
    builtin: true,
    steps: [
      { actionId: 'MOVE_CUP_HOLD' },
      { actionId: 'GRIPPER_GRAB' },
      { actionId: 'MOVE_CUP_MIDDLE' },
      { actionId: 'MOVE_CUP_SPRIAL' },
      { actionId: 'GRIPPER_RELEASE' },
      { actionId: 'MOVE_HOME' },
    ],
  },
  {
    id: 'builtin-cup-measure',
    name: '컵 측정 시퀀스',
    builtin: true,
    steps: [
      { actionId: 'MOVE_HOME' },
      { actionId: 'MOVE_TO_PLATE' },
      { actionId: 'GRIPPER_GRAB' },
      { actionId: 'MOVE_CUP_Z' },
      { actionId: 'CALIBRATE_CUP_Z' },
      { actionId: 'MOVE_TO_PLATE' },
      { actionId: 'GRIPPER_RELEASE' },
      { actionId: 'PUSH_CUP_CORNER' },
      { actionId: 'CALIBRATE_CUP_DIAMETER' },
      { actionId: 'MOVE_HOME' },
    ],
  },
  {
    id: 'builtin-plate-test',
    name: '홈 ↔ 측정판 왕복',
    builtin: true,
    steps: [
      { actionId: 'MOVE_HOME' },
      { actionId: 'MOVE_TO_PLATE' },
      { actionId: 'MOVE_HOME' },
    ],
  },
]

function createUid() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function hydrateStep(raw, actionMap) {
  if (!raw || typeof raw.actionId !== 'string') return null
  if (raw.actionId === WAIT_ACTION.id) {
    const waitSec = Number(raw.waitSec)
    return {
      uid: createUid(),
      actionId: WAIT_ACTION.id,
      waitSec: Number.isFinite(waitSec) && waitSec > 0 ? waitSec : 1.0,
    }
  }
  const action = actionMap.get(raw.actionId)
  if (!action) return null
  return {
    uid: createUid(),
    actionId: action.id,
    param: raw.param ?? action.defaultOption ?? undefined,
  }
}

function serializeStep(step) {
  if (step.actionId === WAIT_ACTION.id) {
    return { actionId: WAIT_ACTION.id, waitSec: Number(step.waitSec) || 1.0 }
  }
  return step.param !== undefined
    ? { actionId: step.actionId, param: step.param }
    : { actionId: step.actionId }
}

function loadSavedSteps(actionMap) {
  try {
    const raw = localStorage.getItem(STORAGE_STEPS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((item) => hydrateStep(item, actionMap)).filter(Boolean)
  } catch {
    return []
  }
}

function loadSavedPresets() {
  try {
    const raw = localStorage.getItem(STORAGE_PRESETS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function useScenarioBuilder({ actions, executeAction, isGlobalBusy }) {
  const actionMapRef = useRef(new Map())
  actionMapRef.current = new Map(actions.map((action) => [action.id, action]))

  const [steps, setSteps] = useState(() => loadSavedSteps(actionMapRef.current))
  const [customPresets, setCustomPresets] = useState(loadSavedPresets)
  const [isRunning, setIsRunning] = useState(false)
  const [runningIndex, setRunningIndex] = useState(-1)
  const [stepStatuses, setStepStatuses] = useState({})
  const [statusFeedback, setStatusFeedback] = useState(null)

  const abortRequestedRef = useRef(false)
  const stepsRef = useRef(steps)
  stepsRef.current = steps

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_STEPS_KEY, JSON.stringify(steps.map(serializeStep)))
    } catch {
      // ignore storage quota errors
    }
  }, [steps])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_PRESETS_KEY, JSON.stringify(customPresets))
    } catch {
      // ignore storage quota errors
    }
  }, [customPresets])

  const addStep = useCallback((actionId, param, insertIndex = null) => {
    const hydrated = hydrateStep(
      actionId === WAIT_ACTION.id
        ? { actionId, waitSec: Number(param) || 1.0 }
        : { actionId, param },
      actionMapRef.current,
    )
    if (!hydrated) return

    setSteps((prev) => {
      if (insertIndex === null || insertIndex < 0 || insertIndex >= prev.length) {
        return [...prev, hydrated]
      }
      const next = [...prev]
      next.splice(insertIndex, 0, hydrated)
      return next
    })
    setStepStatuses({})
    setStatusFeedback(null)
  }, [])

  const moveStep = useCallback((fromIndex, toIndex) => {
    setSteps((prev) => {
      if (
        fromIndex < 0 ||
        fromIndex >= prev.length ||
        toIndex < 0 ||
        toIndex > prev.length ||
        fromIndex === toIndex
      ) {
        return prev
      }
      const next = [...prev]
      const [moved] = next.splice(fromIndex, 1)
      const adjustedIndex = toIndex > fromIndex ? toIndex - 1 : toIndex
      next.splice(adjustedIndex, 0, moved)
      return next
    })
    setStepStatuses({})
    setStatusFeedback(null)
  }, [])

  const removeStep = useCallback((uid) => {
    setSteps((prev) => prev.filter((item) => item.uid !== uid))
    setStepStatuses({})
    setStatusFeedback(null)
  }, [])

  const updateStepParam = useCallback((uid, param) => {
    setSteps((prev) =>
      prev.map((item) => (item.uid === uid ? { ...item, param } : item)),
    )
  }, [])

  const updateStepWait = useCallback((uid, waitSec) => {
    const safeSec = Math.max(0.1, Math.min(60, Number(waitSec) || 0.5))
    setSteps((prev) =>
      prev.map((item) => (item.uid === uid ? { ...item, waitSec: safeSec } : item)),
    )
  }, [])

  const clearSteps = useCallback(() => {
    setSteps([])
    setStepStatuses({})
    setStatusFeedback(null)
  }, [])

  const loadPreset = useCallback((preset) => {
    const next = (preset.steps || [])
      .map((raw) => hydrateStep(raw, actionMapRef.current))
      .filter(Boolean)
    setSteps(next)
    setStepStatuses({})
    setStatusFeedback({
      tone: 'neutral',
      message: `'${preset.name}' 시나리오(${next.length}단계)를 불러왔습니다.`,
    })
  }, [])

  const savePreset = useCallback((name) => {
    const trimmed = name.trim()
    if (!trimmed || stepsRef.current.length === 0) return false
    const entry = {
      id: `custom-${createUid()}`,
      name: trimmed,
      builtin: false,
      steps: stepsRef.current.map(serializeStep),
    }
    setCustomPresets((prev) => [entry, ...prev].slice(0, 12))
    setStatusFeedback({
      tone: 'success',
      message: `'${trimmed}' 프리셋을 저장했습니다.`,
    })
    return true
  }, [])

  const deletePreset = useCallback((presetId) => {
    setCustomPresets((prev) => prev.filter((item) => item.id !== presetId))
  }, [])

  const stopScenario = useCallback(() => {
    abortRequestedRef.current = true
    setStatusFeedback({
      tone: 'neutral',
      message: '중단 요청됨: 현재 실행 중인 동작이 끝나면 다음 단계를 멈춥니다.',
    })
  }, [])

  const runScenario = useCallback(async () => {
    const queue = stepsRef.current
    if (queue.length === 0 || isRunning || isGlobalBusy) return

    abortRequestedRef.current = false
    setIsRunning(true)
    setStepStatuses(Object.fromEntries(queue.map((item) => [item.uid, 'pending'])))
    setStatusFeedback({
      tone: 'neutral',
      message: `총 ${queue.length}단계 시나리오 순차 실행을 시작합니다.`,
    })

    for (let idx = 0; idx < queue.length; idx += 1) {
      if (abortRequestedRef.current) {
        setRunningIndex(-1)
        setIsRunning(false)
        setStatusFeedback({
          tone: 'error',
          message: `${idx + 1}단계 시작 전 사용자 요청으로 시나리오가 중단되었습니다.`,
        })
        return
      }

      const step = queue[idx]
      setRunningIndex(idx)
      setStepStatuses((prev) => ({ ...prev, [step.uid]: 'running' }))

      if (step.actionId === WAIT_ACTION.id) {
        const totalMs = Math.max(100, Math.round((Number(step.waitSec) || 1.0) * 1000))
        const started = Date.now()
        while (Date.now() - started < totalMs) {
          if (abortRequestedRef.current) {
            setStepStatuses((prev) => ({ ...prev, [step.uid]: 'stopped' }))
            setRunningIndex(-1)
            setIsRunning(false)
            setStatusFeedback({
              tone: 'error',
              message: `${idx + 1}단계(대기) 중 사용자 요청으로 중단되었습니다.`,
            })
            return
          }
          await new Promise((resolve) => setTimeout(resolve, 100))
        }
        setStepStatuses((prev) => ({ ...prev, [step.uid]: 'success' }))
        continue
      }

      const action = actionMapRef.current.get(step.actionId)
      if (!action) {
        setStepStatuses((prev) => ({ ...prev, [step.uid]: 'error' }))
        setRunningIndex(-1)
        setIsRunning(false)
        setStatusFeedback({
          tone: 'error',
          message: `${idx + 1}단계(${step.actionId}) 정의를 찾을 수 없어 중단되었습니다.`,
        })
        return
      }

      const res = await executeAction(action, step.param)
      if (!res?.success) {
        setStepStatuses((prev) => ({ ...prev, [step.uid]: 'error' }))
        setRunningIndex(-1)
        setIsRunning(false)
        setStatusFeedback({
          tone: 'error',
          message: `${idx + 1}단계 '${action.title}' 실패로 중단됨: ${res?.message || '오류 발생'}`,
        })
        return
      }

      setStepStatuses((prev) => ({ ...prev, [step.uid]: 'success' }))
    }

    setRunningIndex(-1)
    setIsRunning(false)
    setStatusFeedback({
      tone: 'success',
      message: `시나리오 ${queue.length}단계가 모두 정상 완료되었습니다.`,
    })
  }, [executeAction, isGlobalBusy, isRunning])

  return {
    steps,
    presets: [...BUILT_IN_SCENARIO_PRESETS, ...customPresets],
    isRunning,
    runningIndex,
    stepStatuses,
    statusFeedback,
    addStep,
    moveStep,
    removeStep,
    updateStepParam,
    updateStepWait,
    clearSteps,
    loadPreset,
    savePreset,
    deletePreset,
    runScenario,
    stopScenario,
  }
}
