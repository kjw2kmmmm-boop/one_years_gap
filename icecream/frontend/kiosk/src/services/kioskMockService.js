/**
 * 백엔드 연동 전 키오스크 UI 테스트용 목업 서비스.
 * 추후 /measure, /ws/measuring, /order, /ws/order-progress API로 교체한다.
 */

export const CUP_PRESETS = [
  { id: 'small', label: '소형 컵', heightZ: 85.0, diameter: 78.0 },
  { id: 'medium', label: '중형 컵', heightZ: 115.0, diameter: 90.0 },
  { id: 'large', label: '대형 컵', heightZ: 142.0, diameter: 102.0 },
]

export const FLAVORS = [
  {
    id: 'CHOCO',
    name: '초코',
    engName: 'CHOCOLATE',
    desc: '진하고 부드러운 다크 초콜릿 스쿱',
    swatch: '#6b4f3f',
    softBg: '#f1ebe6',
  },
  {
    id: 'STRAWBERRY',
    name: '딸기',
    engName: 'STRAWBERRY',
    desc: '상큼하고 달콤한 딸기 과육 스쿱',
    swatch: '#b86868',
    softBg: '#f6eaea',
  },
]

export const MEASURE_STEPS = [
  { phase: 'APPROACHING', label: '측정 위치로 이동 중', progress: 22 },
  { phase: 'PROBING_Z', label: '컵 상단 높이(Z) 접촉 측정 중', progress: 58 },
  { phase: 'PROBING_DIAMETER', label: '컵 직경 규격 확인 중', progress: 84 },
  { phase: 'RETRACTING', label: '측정판 원위치 복귀 중', progress: 100 },
]

export const SCOOP_STAGES = [
  { stage: 'SURFACE_PROBING', label: '아이스크림 표면 탐색' },
  { stage: 'PENETRATING', label: '스쿱 진입 중' },
  { stage: 'CURLING', label: '아이스크림 말아올리기' },
  { stage: 'LIFTING', label: '컵으로 이동 및 담기' },
]

/**
 * 측정된 컵 높이(mm)에 따라 담을 수 있는 최대 스쿱 개수를 계산한다.
 */
export function calculateMaxScoops(heightZ) {
  if (heightZ >= 135) return 4
  if (heightZ >= 105) return 3
  return 2
}

export function createMockOrderId() {
  const num = Math.floor(100 + Math.random() * 900)
  return `ICE-${num}`
}
