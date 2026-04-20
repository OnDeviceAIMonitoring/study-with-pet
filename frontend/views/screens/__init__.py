"""
screens 패키지 - 각 화면(스크린) Mixin 모듈

- main.py       : MainScreenMixin   (메인 화면)
- character.py  : CharScreenMixin   (캐릭터 선택/목록/생성)
- group.py      : GroupScreenMixin  (단체방)
- camera.py     : CameraScreenMixin (카메라 피드)
- daily_goal_time_setting.py : DailyGoalTimeSettingScreenMixin (목표 시간 입력)
"""

from .main import MainScreenMixin
from .character import CharScreenMixin
from .group import GroupScreenMixin
from .study_flow import StudyFlowMixin
from .group_study import GroupStudyMixin
from .personal_study import PersonalStudyMixin
from .study_growth import StudyGrowthMixin
from .camera import CameraScreenMixin
from .daily_goal_time_setting import DailyGoalTimeSettingScreenMixin

__all__ = [
    "MainScreenMixin",
    "CharScreenMixin",
    "GroupScreenMixin",
    "StudyFlowMixin",
    "GroupStudyMixin",
    "PersonalStudyMixin",
    "StudyGrowthMixin",
    "CameraScreenMixin",
    "DailyGoalTimeSettingScreenMixin",
]
