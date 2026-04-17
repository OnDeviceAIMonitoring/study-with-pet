"""
리팩토링된 엔트리포인트: 모듈화된 Viewer를 실행합니다.

이 파일은 인수 파싱과 `ViewerApp` 실행만 담당합니다.
"""

import argparse

from views.app import ViewerApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Digital Pet room video viewer (CustomTkinter)")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--room", default="TEST_ROOM")
    parser.add_argument("--name", default="viewer_user")
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--window-title", default="Digital Pet Room Viewer")
    parser.add_argument("--canvas-width", type=int, default=1024)
    parser.add_argument("--canvas-height", type=int, default=600)
    parser.add_argument("--left-reserved-width", type=int, default=300)
    parser.add_argument("--main-width", type=int, default=430)
    parser.add_argument("--main-height", type=int, default=320)
    parser.add_argument("--sub-width", type=int, default=140)
    parser.add_argument("--sub-height", type=int, default=105)
    parser.add_argument("--refresh-ms", type=int, default=50)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = ViewerApp(args)
    app.start()
