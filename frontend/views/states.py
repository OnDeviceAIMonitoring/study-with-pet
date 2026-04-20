"""
앱 상태를 관리하는 데이터 클래스들

각 도메인별로 상태를 객체화하여 산재된 변수를 줄입니다.
"""

import threading
from dataclasses import dataclass, field


@dataclass
class CameraState:
    """카메라 렌더링 상태"""
    running: bool = False
    thread: threading.Thread = None
    latest_frame: object = None
    
    # 애니메이션 프레임 정보
    char_frames: list = field(default_factory=list)
    char_frame_idx: int = 0
    char_anim_running: bool = False
    
    # 시그널 기반 애니메이션 전환
    anim_sets: dict = field(default_factory=dict)  # {"happy": [...], "tail": [...], "tear": [...]}
    current_anim: str = "tail"
    signal_lock: threading.Lock = field(default_factory=threading.Lock)
    current_signal: str = None


@dataclass
class PersonalStudyState:
    """개인 공부 세션 상태"""
    timer_running: bool = False
    start_time: float = 0.0
    elapsed_seconds: int = 0
    accumulated_points: int = 0
    blocked_slots: set = field(default_factory=set)
    
    # 캐릭터 상태
    char_id: object = None
    char_idx: int = -1
    char_name: str = ""
    char_growth_percent: float = 0.0
    
    # 애니메이션
    anim_sets: dict = field(default_factory=dict)
    current_anim: str = "tail"


@dataclass
class GroupStudyState:
    """그룹 공부 세션 상태"""
    running: bool = False
    start_time: float = 0.0
    elapsed_seconds: int = 0
    accumulated_points: int = 0
    blocked_slots: set = field(default_factory=set)
    
    # 캐릭터 오버레이
    char_frames: list = field(default_factory=list)
    char_frame_idx: int = 0
    char_last_tick: float = 0.0
    char_name: str = ""
    char_growth_percent: float = 0.0
    char_idx: int = -1
    char_id: object = None
    char_anim_running: bool = False
    char_anim_sets: dict = field(default_factory=dict)
    char_current_anim: str = "tail"


@dataclass
class NavigationState:
    """네비게이션/선택 상태"""
    pending_group_room: tuple = None  # (room_code, room_name) or None
    selected_char: object = None
