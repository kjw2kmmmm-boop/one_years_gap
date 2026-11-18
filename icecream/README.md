# Icecream Cobot Project (`ws_cobot_pjt`)

Doosan M0609 협동로봇 + OnRobot RG2 그리퍼 기반 아이스크림 제조 자동화 프로젝트입니다.  
ROS2 Jazzy 제어 노드, FastAPI 백엔드(ROS2 브리지 포함), React 대시보드·키오스크 프론트엔드로 구성되어 있습니다.

- 시스템 아키텍처 다이어그램: [`docs/img/icecream_full.drawio.png`](docs/img/icecream_full.drawio.png)
- 로봇 하드웨어·시뮬레이션 상세 가이드: [`ws_dsr/src/README.md`](ws_dsr/src/README.md)

---

## 디렉토리 구조

```text
ws_cobot_pjt/
├── backend/                     # FastAPI 백엔드 (Python 3.14, uv)
│   └── app/
│       ├── api/endpoints/       # dashboard.py, orders.py, measure.py
│       ├── ros_bridge/          # ROS2 Python 3.12 서비스/토픽 브리지 워커
│       ├── schemas/             # Pydantic 요청·응답 스키마
│       ├── services/            # DashboardService, TelemetryService
│       └── main.py              # FastAPI 엔트리포인트 (lifespan, CORS)
├── frontend/
│   ├── dashboard/               # 로봇 제어 & 실시간 텔레메트리 대시보드 (React + Vite, :5173)
│   └── kiosk/                   # 고객 주문 키오스크 UI 목업 (React + Vite, :3000)
├── ws_dsr/                      # ROS2 Jazzy 워크스페이스 (Python 3.12)
│   └── src/
│       ├── icecream_interfaces/     # 커스텀 msg / srv / action
│       ├── icecream_motion_manager/ # /execute_task 서버 및 단위 모션 + poses.yaml
│       ├── icecream_system_status/  # /dashboard/telemetry 퍼블리셔 노드
│       ├── icecream_bringup/        # 통합 launch 패키지
│       ├── icecream_order_manager/  # 주문 오케스트레이션 (스켈레톤)
│       ├── rg2/m0609_rg2_bringup/   # M0609 + RG2 브링업 패키지
│       ├── doosan-robot2/           # Doosan ROS2 드라이버 (외부 패키지)
│       ├── onrobot-ros2/            # OnRobot RG2 드라이버 (외부 패키지)
│       └── rokey1/                  # 단위 모션 테스트 스크립트
├── docs/                        # 설계 문서 및 이미지
├── deploy/                      # 배포 설정 스켈레톤 (nginx, scripts)
└── data/                        # 데이터 저장소 디렉토리
```

---

## 1. ROS2 워크스페이스 (`ws_dsr`)

### 주요 패키지 및 인터페이스

| 패키지 | 역할 |
|---|---|
| `icecream_interfaces` | `ExecuteTask.srv`, `MoveToFlavor.srv`, `MoveToScoop.srv`, `MeasureCup.action`, `ScoopFlavor.action`, `SystemTelemetry.msg`, `MotionDiagnostics.msg` |
| `icecream_motion_manager` | `/execute_task` 서비스 서버, `/motion/diagnostics` 발행, 단위 모션 실행 및 `config/poses.yaml` 관리 |
| `icecream_system_status` | `/motion/diagnostics`, `/tf`, `/dsr01/joint_states`, `dsr_controller2` 상태를 취합해 `/dashboard/telemetry` (`SystemTelemetry`) 발행 (10Hz) |
| `icecream_bringup` | `m0609_rg2_bringup` + `motion_manager` + `system_status` 통합 실행 launch |

### 구현된 `ExecuteTask` 명령 (`icecream_motion_manager`)
모든 모션 좌표 및 속도/가속도는 [`ws_dsr/src/icecream_motion_manager/config/poses.yaml`](ws_dsr/src/icecream_motion_manager/config/poses.yaml)에서 관리하며, 비동기 모션(`amovej`/`amovel`) + `check_motion()` 대기 방식으로 동작 중에도 텔레메트리 조회가 블로킹되지 않습니다.

| `command` | `target` | 동작 |
|---|---|---|
| `MOVE_HOME` | `""` | `home` 관절 좌표 이동 후 그리퍼 열기 |
| `MOVE_TO_SCOOP` | `""` | 현재 Z 높이 유지 수평 이동 후 `scoop` Z로 수직 하강 |
| `MOVE_CUP_Z` | `""` | `cup_z` 컵 측정 위치로 직선 이동 |
| `MOVE_TO_PLATE` | `""` | `plate` 측정판 손잡이 위치로 직선 이동 |
| `MOVE_TO_FLAVOR` | `CHOCO` \| `STRAWBERRY` | 선택한 맛 통 위치로 직선 이동 |
| `GRIP_AND_LIFT` | `""` | 그리퍼 닫기 후 Z축 상대 상승 (`+150mm`) |
| `GRIPPER_RELEASE` | `""` | 그리퍼 열기 (`DO1=0`, `DO2=1` 펄스) |
| `GRIPPER_GRAB` | `""` | 그리퍼 닫기 (`DO2=0`, `DO1=1` 펄스) |
| `CALIBRATE_CUP_Z` | `""` | 하강 중 Z축 외력 접촉 감지로 컵 높이 측정 후 원위치 복귀 (`latest_cup_height_z` 갱신) |

### 빌드 및 실행

> 백엔드 `.venv`(Python 3.14)가 활성화된 터미널에서는 CMake가 Python 3.14를 잡아 `catkin_pkg` 오류가 날 수 있으므로 `-DPython3_EXECUTABLE=/usr/bin/python3` 옵션을 함께 사용하세요.

```bash
cd /home/ubuntu/ws_cobot_pjt/ws_dsr
colcon build --packages-select icecream_interfaces icecream_motion_manager icecream_system_status icecream_bringup --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash
```

- **통합 실행 (Virtual 시뮬레이션 + 모션/상태 노드)**
  ```bash
  ros2 launch icecream_bringup icecream_bringup.launch.py
  ```
- **통합 실행 (Real 실제 로봇 + 모션/상태 노드)**
  ```bash
  ros2 launch icecream_bringup icecream_bringup.launch.py mode:=real host:=192.168.1.100
  ```
  *(카메라 포함 시 `camera:=true` 추가)*
- **`icecream_*` 노드만 별도 실행**
  ```bash
  ros2 launch icecream_bringup icecream_nodes.launch.py
  ```

> **네트워크/도메인 주의**: 여러 PC가 같은 서브넷에 있을 때 `~/.bashrc`의 `ROS_DISCOVERY_SERVER` 또는 `ROS_DOMAIN_ID`가 다르면 노드 간 연결이 어긋날 수 있습니다. 로컬 단독 시뮬레이션 시 모든 터미널(브링업·노드·백엔드)에서 `unset ROS_DISCOVERY_SERVER ROS_SUPER_CLIENT`, `export ROS_DOMAIN_ID=<동일값>`을 맞춰 실행하세요.

---

## 2. 백엔드 (`backend`)

FastAPI 서버(Python 3.14)가 `ros_bridge`의 Python 3.12 워커 스크립트(`ros_task_caller.py`, `ros_telemetry_subscriber.py`)를 통해 ROS2 서비스 호출 및 토픽 구독을 수행합니다.

### 주요 엔드포인트 (`dashboard.py`)

| Method / Protocol | Path | 설명 |
|---|---|---|
| `GET` | `/` | 백엔드 헬스 체크 |
| `POST` | `/home` | `MOVE_HOME` 실행 |
| `POST` | `/move-to-scoop` | `MOVE_TO_SCOOP` 실행 |
| `POST` | `/move-cup-z` | `MOVE_CUP_Z` 실행 |
| `POST` | `/move-to-plate` | `MOVE_TO_PLATE` 실행 |
| `POST` | `/move-to-flavor` | `MOVE_TO_FLAVOR` 실행 (`{"flavor": "CHOCO" \| "STRAWBERRY"}`) |
| `POST` | `/grip-and-lift` | `GRIP_AND_LIFT` 실행 |
| `POST` | `/gripper-release` | `GRIPPER_RELEASE` 실행 |
| `POST` | `/gripper-grab` | `GRIPPER_GRAB` 실행 |
| `POST` | `/calibrate-cup-z` | `CALIBRATE_CUP_Z` 실행 (timeout `190s`) |
| `GET` | `/telemetry` | 최신 `SystemTelemetry` 스냅샷 조회 |
| `WS` | `/ws/telemetry` | 실시간 `SystemTelemetry` WebSocket 스트림 |

*(추후 구현 예정 스켈레톤: `/orders`, `/order`, `/ws/order-progress`, `/measure`, `/ws/measuring`)*

### 실행

```bash
cd /home/ubuntu/ws_cobot_pjt/backend/app
/home/ubuntu/ws_cobot_pjt/backend/.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 3. 프론트엔드 (`frontend`)

### 대시보드 (`frontend/dashboard`, 포트 `5173`)
- 실시간 텔레메트리 모니터링(`WS /ws/telemetry` + `GET /telemetry`) 및 수동 모션 제어/실행 이력 확인.
- Vite 프록시(`/api` → `http://127.0.0.1:8000`, `ws: true`)로 백엔드와 연동됩니다.

```bash
cd /home/ubuntu/ws_cobot_pjt/frontend/dashboard
npm install
npm run dev -- --host 0.0.0.0
```

### 키오스크 (`frontend/kiosk`, 포트 `3000`)
- 현재 백엔드 미연동 목업(Mockup) 상태이며, 고객 주문 플로우를 구현했습니다:
  1. 컵 투입 안내 (`측정 시작`)
  2. 컵 측정 진행 (`APPROACHING` → `PROBING_Z` → `PROBING_DIAMETER` → `RETRACTING`)
  3. 아이스크림 유형 선택 (`소프트 아이스크림` 준비 중 안내 / `컵 아이스크림`)
  4. 측정된 컵 높이에 따른 최대 스쿱 수량 안내 및 맛 선택 (`초코`, `딸기`)
  5. 스쿠핑 제조 진행
  6. 제조 완료 요약 및 초기화

```bash
cd /home/ubuntu/ws_cobot_pjt/frontend/kiosk
npm install
npm run dev -- --host 0.0.0.0
```
