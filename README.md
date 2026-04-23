# 🐾 Study With Pet

> **웹캠 AI 기반 학습 집중 도우미** — 공부하는 동안 나만의 디지털 펫이 함께 성장합니다.

**Study With Pet**은 웹캠 영상을 실시간으로 분석하여 **졸음**, **딴 짓**, **산만함**을 감지하고, 집중할수록 성장하는 디지털 펫과 함께 학습 효율을 높이는 데스크톱 애플리케이션입니다.

---

## ✨ 주요 기능

### 🤖 AI 실시간 행동 분석
- **졸음 감지** — EAR(Eye Aspect Ratio) 기반 눈 감김 + Pose Pitch 기반 고개 숙임 탐지
- **딴 짓 감지** — 고개 방향 이탈, 핸드폰/방해요소 객체 탐지(YOLO), 웃으면서 대화, 화면 이탈
- **산만함 감지** — 상반신 키포인트 이동량 분석을 통한 반복적 움직임(fidget) 감지
- **하트 제스처** — 양손 하트를 펫에게 보내면 행복 애니메이션 반응

### 🐶 디지털 펫 성장 시스템
- **5종 캐릭터**: 말티즈, 요크셔테리어, 토끼, 보더콜리, 앵그리 고블린(알람용)
- **3단계 성장**: Baby → Adult → Crown (집중 시간에 비례하여 성장)
- **실시간 반응**: 집중 시 꼬리 흔들기, 졸음/딴 짓 시 눈물, 하트 제스처 시 행복 표정

### 👥 그룹 스터디
- **실시간 화상 공유** — Socket.IO 기반 카메라 피드 브로드캐스트
- **공동 목표** — 모든 멤버가 공부 중일 때만 그룹 타이머 진행
- **방 관리** — 방 생성/참여 코드 공유

### 📊 학습 관리
- **일일 목표 설정** — 시간/분 단위 목표 설정 및 달성률 추적
- **연속 달성 스트릭** — 목표 달성 연속 일수 표시
- **진행률 바** — 파란색(학습 중), 회색(일시정지), 빨간색(경고), 노란색(목표 달성)

---

## 🏗️ 시스템 아키텍처

```
study-with-pet/
├── backend/          # FastAPI + Socket.IO 서버, SQLite DB
├── config/           # Detector 설정 (off_task.json 등)
├── detectors/        # AI 감지 모듈 (4종)
│   ├── shared.py     #   MediaPipe Holistic 공유 인스턴스
│   ├── drowsiness.py #   졸음 감지 (EAR + Pose Pitch)
│   ├── fidget.py     #   산만함 감지 (에너지 Burst)
│   ├── off_task.py   #   딴 짓 감지 (Yaw, YOLO, Smile-Talk, Tracker)
│   └── heart.py      #   하트 제스처 감지
├── frontend/         # CustomTkinter UI
│   ├── main.py       #   엔트리포인트
│   ├── views/        #   화면 (메인, 캐릭터, 개인/그룹 스터디, ...)
│   ├── services/     #   비즈니스 로직 (카메라, 캐릭터, 소켓, ...)
│   └── assets/       #   이미지, 사운드 리소스
├── models/           # ONNX 모델 (⚠️ Git 미포함)
└── launch/           # 라즈베리파이 런처 스크립트
```

### AI 파이프라인

```
웹캠 프레임 → SharedMediaPipe (Holistic 1회 추론)
                 ├── DrowsinessDetector → DROWSINESS Signal
                 ├── FidgetDetector     → LOW_FOCUS Signal
                 ├── OffTaskDetector    → OFF_TASK Signal
                 │     ├── YOLO ONNX (객체 탐지, 비동기)
                 │     ├── Head Yaw (시선 이탈)
                 │     ├── Smile-Talking (대화 탐지)
                 │     └── Kalman Tracker (화면 이탈)
                 └── HeartDetector      → HEART Signal
```

> 알고리즘 상세 설명은 [detector_algorithm.md](detectors/detector_algorithm.md) 참조

---

## 🔧 요구 사항

| 항목 | 요구 사항 |
|------|-----------|
| **Python** | 3.10 이상 |
| **OS** | Windows / Linux / macOS |
| **하드웨어** | 웹캠 필수, 스피커(알람음 재생) |
| **네트워크** | 그룹 스터디 시 LAN 연결 |

### 주요 의존성

| 패키지 | 용도 |
|--------|------|
| `customtkinter` | UI 프레임워크 |
| `opencv-contrib-python` | 카메라 입력 및 영상 처리 |
| `mediapipe` | 얼굴/포즈/손 랜드마크 추론 |
| `onnxruntime` | YOLO 객체 탐지 추론 |
| `fastapi` + `python-socketio` | 서버 및 실시간 통신 |
| `sounddevice` | 알람 사운드 재생 |

---

## 🚀 설치 및 실행

### 1. 클론 및 환경 설정

```bash
git clone https://github.com/<your-org>/study-with-pet.git
cd study-with-pet
python -m venv .venv
```

**Linux / macOS:**
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows PowerShell:**
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 모델 다운로드

Off-Task 감지에 필요한 YOLO ONNX 모델은 Git에 포함되지 않습니다.  
아래 안내에 따라 다운로드 후 `models/` 디렉토리에 저장하세요.

> 📥 [models/model.md](models/model.md) 참고

### 3. 서버 실행

```bash
uvicorn backend.server:socket_app --host 0.0.0.0 --port 8000 --reload
```

### 4. 클라이언트 실행

```bash
python frontend/main.py \
  --server http://127.0.0.1:8000 \
  --room ROOM_CODE \
  --name 사용자이름
```

> **LAN 환경**에서는 `127.0.0.1` 대신 서버 PC의 IP를 사용합니다.  
> 예: `--server http://192.168.0.10:8000`

### (선택) 한글 폰트 설치 (Linux)

```bash
sudo apt update
sudo apt install -y fonts-nanum fonts-unfonts-core
sudo fc-cache -fv
```

---

## ⚙️ 실행 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--server` | `http://127.0.0.1:8000` | 서버 주소 |
| `--room` | `TEST_ROOM` | 방 코드 |
| `--name` | `viewer_user` | 사용자 이름 |
| `--duration` | `0` (무제한) | 학습 시간(초) |
| `--window-title` | `Study With Pet` | 창 제목 |
| `--canvas-width` | `1024` | 캔버스 너비 |
| `--canvas-height` | `600` | 캔버스 높이 |
| `--refresh-ms` | `50` | 렌더링 주기(ms) |

---

## 🐛 문제 해결

| 증상 | 해결 방법 |
|------|-----------|
| `ModuleNotFoundError` | 가상환경 활성화 확인 후 `pip install -r requirements.txt` 재실행 |
| 카메라 열기 실패 | `--camera-device` 번호 확인, OS 카메라 권한 허용 |
| 서버 접속 실패 | 서버 실행 상태 확인, 방화벽 포트 8000 허용 |
| YOLO 모델 미로드 | `models/yolo26n.onnx` 파일 존재 여부 확인 ([다운로드 안내](models/model.md)) |

---

## 📖 문서

- [detector_algorithm.md](detectors/detector_algorithm.md) — AI 탐지 알고리즘 상세 (졸음, 딴 짓, 산만함, 하트 — 수식 및 순서도 포함)
- [pet.md](pet.md) — 펫 시스템 설계
- [models/model.md](models/model.md) — ONNX 모델 다운로드 안내

---

## 👥 저자

| <a href="https://github.com/Jaehwan0501"><img src="https://github.com/Jaehwan0501.png" width="80"/><br/>이재환</a> | <a href="https://github.com/Jeong-ae"><img src="https://github.com/Jeong-ae.png" width="80"/><br/>이정애</a> | <a href="https://github.com/rainshowerr"><img src="https://github.com/rainshowerr.png" width="80"/><br/>신서영</a> | <a href="https://github.com/CSEDTD"><img src="https://github.com/CSEDTD.png" width="80"/><br/>윤성우</a> |
|:---:|:---:|:---:|:---:|