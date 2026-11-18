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

export function calibrateCupZ() {
  return requestJson('/calibrate-cup-z', { method: 'POST' })
}

export function fetchTelemetry() {
  return requestJson('/telemetry', { method: 'GET' })
}

export function getTelemetryWebSocketUrl() {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return `${import.meta.env.VITE_WS_BASE_URL.replace(/\/$/, '')}/ws/telemetry`
  }
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    return `${API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')}/ws/telemetry`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const prefix = API_BASE.startsWith('/') ? API_BASE : `/${API_BASE}`
  return `${protocol}//${window.location.host}${prefix.replace(/\/$/, '')}/ws/telemetry`
}
