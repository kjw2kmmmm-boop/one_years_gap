const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

function getWsBaseUrl() {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL.replace(/\/$/, '')
  }
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    return API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const prefix = API_BASE.startsWith('/') ? API_BASE : `/${API_BASE}`
  return `${protocol}//${window.location.host}${prefix.replace(/\/$/, '')}`
}

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
    const message =
      typeof detail === 'string'
        ? detail
        : typeof detail === 'object' && detail !== null
          ? detail.message || '요청 처리에 실패했습니다.'
          : `HTTP ${response.status} 오류가 발생했습니다.`
    throw new Error(message)
  }

  return body
}

export function createOrder({
  ice_cream_type = 'CUP',
  cup_height_z,
  cup_diameter,
  scoops,
}) {
  return requestJson('/order', {
    method: 'POST',
    body: JSON.stringify({
      ice_cream_type,
      cup_height_z,
      cup_diameter,
      scoops,
    }),
  })
}

export function getOrder(orderCode) {
  return requestJson(`/orders/${encodeURIComponent(orderCode)}`, {
    method: 'GET',
  })
}

export function getMeasureWebSocketUrl() {
  return `${getWsBaseUrl()}/ws/measuring`
}

export function getOrderProgressWebSocketUrl(orderCode) {
  return `${getWsBaseUrl()}/ws/order-progress/${encodeURIComponent(orderCode)}`
}
