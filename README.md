# Digital Pet (PoC)

라즈베리파이/PC 환경에서 동작하는 디지털 펫 프로젝트의 통신 PoC입니다.
현재는 Socket.IO 기반으로 방 입장, 상태 동기화, JPEG 프레임 브로드캐스트를 테스트합니다.

## 프로젝트 구조

```text
pet/
├── backend/          # 서버 (Socket.IO)
├── config/           # Detector 설정 파일
├── detectors/        # 졸음/산만함/딴짓/하트 Detector
├── frontend/         # UI (main.py 실행)
├── models/           # ONNX 모델 (⚠️ Git 미포함 — models/model.md 참고)
└── requirements.txt
```

## 모델 파일 (ONNX)

Off-Task 감지에 필요한 YOLO 모델은 Git에 포함되지 않습니다.  
**Google Drive**에서 다운로드 후 `models/` 디렉토리에 저장하세요.

> 📥 [models/model.md](models/model.md) 참고

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

#### 한글 폰트 설치
```
sudo apt update
sudo apt install -y fonts-nanum fonts-unfonts-core
sudo fc-cache -fv
sudo reboot
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

### 2) 클라이언트 실행 (수신 확인)

```bash
cd /home/willtek/work/pet
source .venv/bin/activate
python frontend/main.py \
  --server http://127.0.0.1:8000 \
  --room TEST_ROOM \
  --name viewer_user
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
