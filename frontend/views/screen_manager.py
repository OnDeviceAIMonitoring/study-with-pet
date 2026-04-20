"""
화면 관리자 - dict 기반 라우팅

show_screen() 메서드의 거대한 if-elif 분기를 제거하고
통일된 방식으로 화면을 관리합니다.
"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ScreenHandler:
    """각 화면에 대한 핸들러"""
    frame: object  # CTkFrame
    on_show: Optional[Callable] = None  # 화면 표시 시 실행
    on_hide: Optional[Callable] = None  # 화면 숨김 시 실행


class ScreenManager:
    """모든 화면의 라우팅을 관리합니다"""
    
    def __init__(self):
        self.screens = {}  # {screen_id: ScreenHandler}
        self._current_screen_id = None
    
    def register(self, screen_id: int, frame: object, 
                 on_show: Optional[Callable] = None, 
                 on_hide: Optional[Callable] = None):
        """화면을 등록합니다"""
        self.screens[screen_id] = ScreenHandler(
            frame=frame,
            on_show=on_show,
            on_hide=on_hide,
        )
    
    def show(self, container: object, screen_id: int, transition_fn: Optional[Callable] = None):
        """화면을 표시합니다
        
        Args:
            container: CTkFrame (부모 컨테이너)
            screen_id: 표시할 화면 ID
            transition_fn: 화면 전환 로직 (모든 자식 숨김 등)
        """
        if screen_id not in self.screens:
            raise ValueError(f"Unknown screen: {screen_id}")
        
        handler = self.screens[screen_id]
        
        # 기존 화면 정리
        if transition_fn:
            transition_fn()
        
        # 현재 화면 숨김 콜백 실행
        if self._current_screen_id is not None:
            prev_handler = self.screens.get(self._current_screen_id)
            if prev_handler and prev_handler.on_hide:
                prev_handler.on_hide()
        
        # 새 화면 표시
        handler.frame.pack(fill="both", expand=True)
        
        # 새 화면 표시 콜백 실행
        if handler.on_show:
            handler.on_show()
        
        self._current_screen_id = screen_id
    
    def get_current_screen(self) -> Optional[int]:
        """현재 표시 중인 화면 ID를 반환합니다"""
        return self._current_screen_id
