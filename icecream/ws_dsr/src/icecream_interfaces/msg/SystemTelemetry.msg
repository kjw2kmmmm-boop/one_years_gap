builtin_interfaces/Time timestamp

# 로봇 하드웨어 상태 (두산 드라이버 기반)
string robot_mode              # "MANUAL", "AUTONOMOUS", "EMERGENCY_STOP"
bool is_emergency_stopped
bool is_robot_moving
float64[6] current_tcp_pose    # [X, Y, Z, Rx, Ry, Rz]
float64[6] joint_torques       # 각 관절 토크
float64 tool_force_z           # Z축 외력 (터치 프로빙 감시용)

# 공정 및 주문 상태
string system_state            # "IDLE", "MEASURING_CUP", "SCOOPING", "DISPENSING", "ERROR"
string current_order_id        # 현재 제조 중인 주문 ID (없으면 빈 문자열)
float32 current_order_progress # 전체 공정 진행률 (0.0 ~ 100.0)

# 리소스 진단
float64 latest_cup_height_z    # 최근 실측된 컵 높이
bool cup_stock_warning         # 컵 잔여 부족 경고
int32 active_error_code        # 0: 정상, 그 외 시스템 에러 코드
