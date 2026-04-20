"""
Signal / BaseDetector — 모든 감지기의 공통 인터페이스
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time


@dataclass
class Signal:
    """하나의 감지 이벤트(시그널)"""
    name:      str              # 시그널 이름  (예: "DROWSINESS", "LOW_FOCUS")
    source:    str              # 발생 모듈   (예: "drowsiness", "fidget")
    level:     float = 0.0     # 심각도 0.0~1.0
    detail:    str   = ""      # 추가 설명
    timestamp: float = field(default_factory=time.time)

    def __repr__(self):
        return f"[{self.source}] {self.name} (lv={self.level:.2f}) {self.detail}"


class BaseDetector(ABC):
    """
    모든 감지기가 구현해야 하는 인터페이스.
    signal_hub.py가 매 프레임마다 process_frame()을 호출하고,
    발생한 Signal 목록을 수집합니다.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """감지기 이름 (예: 'drowsiness', 'fidget')"""
        ...

    @abstractmethod
    def process_frame(self, frame, now: float, shared=None) -> list[Signal]:
        """
        한 프레임을 처리하고, 발생한 Signal 리스트를 반환합니다.
        - frame: BGR numpy 배열 (화면 그리기용)
        - now:   time.time() 타임스탬프
        - shared: SharedMediaPipe 인스턴스 (Holistic 추론 결과 공유)
                  signal_hub.py에서 1번만 추론 후 전달하면 CPU 절약 가능
        반환값이 빈 리스트면 해당 프레임에서 시그널 없음.
        """
        ...

    @abstractmethod
    def draw_hud(self, frame) -> None:
        """디버그/모니터링용 HUD를 frame 위에 그립니다."""
        ...

    def release(self) -> None:
        """자원 정리 (선택)"""
        pass
