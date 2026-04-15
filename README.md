# Digital Pet (PoC)

라즈베리파이/PC 환경에서 동작하는 디지털 펫 프로젝트의 통신 PoC입니다.
현재는 Socket.IO 기반으로 방 입장, 상태 동기화, JPEG 프레임 브로드캐스트를 테스트합니다.

## 프로젝트 구조

```text
pet/
├── backend/
│   └── server.py
├── frontend/
│   ├── client_test.py
│   └── viewer_client.py
├── requirements.txt
└── pet.md
```

## 요구 사항

- Python 3.10+
- Linux/macOS/Windows
- (선택) 카메라 송신/뷰어 테스트 시 OpenCV 사용

## 설치

```bash
cd /home/willtek/work/pet
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
cd C:\path\to\pet
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 실행 방법

### 1) 서버 실행

```bash
cd /home/willtek/work/pet
source .venv/bin/activate
uvicorn backend.server:socket_app --host 0.0.0.0 --port 8000 --reload
```

헬스체크:

```bash
curl http://127.0.0.1:8000/health
```

### 2) 기본 클라이언트 테스트

```bash
cd /home/willtek/work/pet
source .venv/bin/activate
python frontend/client_test.py \
  --server http://127.0.0.1:8000 \
  --room TEST_ROOM \
  --name app_user \
  --duration 10
```

### 3) 영상 송신 테스트

기본 정책:

- `--is-main` 사용 시 기본값 `640x480 @ 15fps`
- 미사용 시 기본값 `320x240 @ 10fps`
- `--fps`, `--frame-width`, `--frame-height`를 지정하면 기본값을 덮어씁니다.

```bash
cd /home/willtek/work/pet
source .venv/bin/activate
python frontend/client_test.py \
  --server http://127.0.0.1:8000 \
  --room TEST_ROOM \
  --name cam_user \
  --send-video \
  --duration 60 \
  --is-main \
  --audio-on
```

실제 카메라 사용 시:

```bash
python frontend/client_test.py \
  --server http://127.0.0.1:8000 \
  --room TEST_ROOM \
  --name cam_user \
  --send-video \
  --use-camera \
  --camera-device 0 \
  --frame-width 640 \
  --frame-height 480 \
  --jpeg-quality 70 \
  --fps 15 \
  --duration 60
```

### 4) 뷰어 실행 (수신 확인)

```bash
cd /home/willtek/work/pet
source .venv/bin/activate
python frontend/viewer_client.py \
  --server http://127.0.0.1:8000 \
  --room TEST_ROOM \
  --name viewer_user
```

1024x600 화면에서 좌측 캐릭터 영역을 예약하고 우측에 영상을 배치하려면:

```bash
python frontend/viewer_client.py \
  --server http://127.0.0.1:8000 \
  --room TEST_ROOM \
  --name viewer_user \
  --canvas-width 1024 \
  --canvas-height 600 \
  --left-reserved-width 300
```

## LAN 테스트 팁

- 같은 로컬 네트워크에서 붙을 때는 `127.0.0.1` 대신 서버 PC의 IP를 사용합니다.
- 예: `--server http://192.168.0.10:8000`

## 주요 옵션 요약

`frontend/client_test.py`:

- `--send-video`: JPEG 프레임 송신 활성화
- `--use-camera`: 실제 카메라 입력 사용
- `--fps`: 초당 프레임 전송 수(미지정 시 메인 15 / 서브 10)
- `--frame-width`, `--frame-height`: 캡처 해상도(미지정 시 메인 640x480 / 서브 320x240)
- `--is-main`: 메인 화면 사용자 여부
- `--audio-on`: 오디오 상태 ON으로 전송

`frontend/viewer_client.py`:

- `--canvas-width`, `--canvas-height`: 전체 캔버스 크기
- `--left-reserved-width`: 좌측 캐릭터 영역 예약 폭
- `--main-width`, `--main-height`: 메인 타일 크기
- `--sub-width`, `--sub-height`: 서브 타일 크기
- `--refresh-ms`: 뷰어 렌더링 주기(ms)

## 문제 해결

- `ModuleNotFoundError` 발생 시:
  - 가상환경 활성화 확인 후 `pip install -r requirements.txt` 재실행
- 카메라 열기 실패 시:
  - `--camera-device` 번호 확인
  - OS 카메라 권한 확인
- 접속 실패 시:
  - 서버 실행 상태 확인
  - 방화벽/포트(8000) 허용 확인
