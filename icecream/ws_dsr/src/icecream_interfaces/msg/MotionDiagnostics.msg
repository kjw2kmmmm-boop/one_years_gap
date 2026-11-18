builtin_interfaces/Time timestamp

# 모션 실행 상태
string system_state            # "IDLE", "MOVE_HOME", "MOVE_TO_SCOOP", "MEASURING_CUP", "SCOOPING", "DISPENSING", "ERROR"
string current_command         # 현재 또는 직전 실행 명령 ("MOVE_HOME", "MOVE_TO_SCOOP" 등)
int32 error_code               # 0: 정상, 1: 모션 에러, 2: 알 수 없는 명령, 3: 강제 중단
string message                 # 상태/오류 상세 메시지

# 선택적 공정/리소스 상태
string current_order_id        # 현재 제조 중인 주문 ID (없으면 빈 문자열)
float32 current_order_progress # 전체 공정 진행률 (0.0 ~ 100.0)
float64 latest_cup_height_z    # 최근 실측된 컵 높이 (mm)
bool cup_stock_warning         # 컵 잔여 부족 경고
