const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

/**
 * FastAPI 응답/에러(detail 문자열 또는 {error_code, message})를 일관된 형태로 파싱한다.
 */
async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  let body = null
  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (!response.ok) {
    const detail = body?.detail
    const errorCode =
      typeof detail === 'object' && detail !== null ? detail.error_code ?? null : null
    const message =
      typeof detail === 'object' && detail !== null
        ? detail.message || '요청 처리에 실패했습니다.'
        : typeof detail === 'string'
          ? detail
          : `HTTP ${response.status} 오류가 발생했습니다.`

    const error = new Error(message)
    error.status = response.status
    error.errorCode = errorCode
    throw error
  }

  return body
}

export function checkBackendHealth() {
  return requestJson('/', { method: 'GET' })
}

export function moveRobotHome() {
  return requestJson('/home', { method: 'POST' })
}

export function moveRobotToScoop() {
  return requestJson('/move-to-scoop', { method: 'POST' })
}

export function moveCupZ() {
  return requestJson('/move-cup-z', { method: 'POST' })
}

export function moveCupHold() {
  return requestJson('/move-cup-hold', { method: 'POST' })
}

export function moveCupMiddle() {
  return requestJson('/move-cup-middle', { method: 'POST' })
}

export function moveCupSprial() {
  return requestJson('/move-cup-sprial', { method: 'POST' })
}

export function moveToPlate() {
  return requestJson('/move-to-plate', { method: 'POST' })
}

export function moveToFlavor(flavor) {
  return requestJson('/move-to-flavor', {
    method: 'POST',
    body: JSON.stringify({ flavor }),
  })
}

export function gripAndLift() {
  return requestJson('/grip-and-lift', { method: 'POST' })
}

export function gripperRelease() {
  return requestJson('/gripper-release', { method: 'POST' })
}

export function gripperGrab() {
  return requestJson('/gripper-grab', { method: 'POST' })
}

export function gripperCup() {
  return requestJson('/gripper-cup', { method: 'POST' })
}

export function calibrateCupZ() {
  return requestJson('/calibrate-cup-z', { method: 'POST' })
}

export function pushCupCorner() {
  return requestJson('/push-cup-corner', { method: 'POST' })
}

export function calibrateCupDiameter() {
  return requestJson('/calibrate-cup-diameter', { method: 'POST' })
}

export function scoopIcecream() {
  return requestJson('/scoop-icecream', { method: 'POST' })
}

export function flattenIcecream() {
  return requestJson('/flatten-icecream', { method: 'POST' })
}

export function releaseScoop() {
  return requestJson('/release-scoop', { method: 'POST' })
}

export function fetchTelemetry() {
  return requestJson('/telemetry', { method: 'GET' })
}

export function fetchActionLogs(limit = 12) {
  return requestJson(`/action-logs?limit=${limit}&source=DASHBOARD`, { method: 'GET' })
}

export function clearActionLogs() {
  return requestJson('/action-logs?source=DASHBOARD', { method: 'DELETE' })
}

export function fetchOrders({ limit = 20, status = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) {
    params.set('status', status)
  }
  return requestJson(`/orders?${params.toString()}`, { method: 'GET' })
}

export function getTelemetryWebSocketUrl() {
  return getWebSocketUrl('/ws/telemetry')
}

export function getManualJogWebSocketUrl() {
  return getWebSocketUrl('/manual/ws/jog')
}

export function getScriptRunnerWebSocketUrl() {
  return getWebSocketUrl('/manual/ws/script')
}

export function getScriptStatusWebSocketUrl() {
  return getWebSocketUrl('/manual/ws/script-status')
}

export function fetchScriptRunnerStatus() {
  return requestJson('/manual/script/status', { method: 'GET' })
}

function getWebSocketUrl(wsPath) {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return `${import.meta.env.VITE_WS_BASE_URL.replace(/\/$/, '')}${wsPath}`
  }
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    return `${API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')}${wsPath}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const prefix = API_BASE.startsWith('/') ? API_BASE : `/${API_BASE}`
  return `${protocol}//${window.location.host}${prefix.replace(/\/$/, '')}${wsPath}`
}

export function manualStep(payload) {
  return requestJson('/manual/step', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function manualStop(stop_mode = 1) {
  return requestJson('/manual/stop', {
    method: 'POST',
    body: JSON.stringify({ stop_mode }),
  })
}

export function manualSetSpeed(speed) {
  return requestJson('/manual/speed', {
    method: 'POST',
    body: JSON.stringify({ speed }),
  })
}

export function manualSetMode(robot_mode) {
  return requestJson('/manual/mode', {
    method: 'POST',
    body: JSON.stringify({ robot_mode }),
  })
}

export function stopManualScript() {
  return requestJson('/manual/script/stop', {
    method: 'POST',
  })
}
