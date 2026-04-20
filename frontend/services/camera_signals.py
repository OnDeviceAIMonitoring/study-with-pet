"""카메라 시그널과 캐릭터 애니메이션 매핑 상수."""

# 시그널 -> 캐릭터 애니메이션 매핑
SIGNAL_TO_ANIM = {
    "HEART": "happy",      # 하트 제스처 -> 기쁨
    "DROWSINESS": "tear",  # 졸음 -> 걱정/눈물
    "OFF_TASK": "tear",    # 딴짓 -> 걱정/눈물
    "LOW_FOCUS": "tear",   # 산만 -> 걱정/눈물
}
DEFAULT_ANIM = "tail"        # 시그널 없음 -> 꼬리 흔들기 (평상시)

# 시그널 우선순위 (앞에 있을수록 우선)
SIGNAL_PRIORITY = ["DROWSINESS", "OFF_TASK", "LOW_FOCUS", "HEART"]

# 시그널 종류별 색상/라벨 (카메라 영상 알림 바용)
SIGNAL_STYLES = {
    "DROWSINESS": {"color": (0, 0, 200), "label": "DROWSINESS"},
    "OFF_TASK": {"color": (252, 180, 14), "label": "OFF_TASK"},
    "LOW_FOCUS": {"color": (0, 100, 220), "label": "LOW_FOCUS"},
    "HEART": {"color": (180, 0, 180), "label": "BIG HEART!"},
}
DEFAULT_STYLE = {"color": (180, 180, 0), "label": "alarm"}
