# AI 집중력 케어 '디지털 펫' 프로젝트 구현 계획서 (Raspberry Pi Client + Laptop Server)

## 0. 프로젝트 개요

| 항목            | 내용                                                                                                         |
| --------------- | ------------------------------------------------------------------------------------------------------------ |
| **프로젝트명**  | AI 집중력 케어 디지털 펫                                                                                     |
| **목표**        | AI 비전 기술로 사용자의 집중 상태를 실시간 분석하고, 디지털 펫 캐릭터를 통해 동기 부여 및 집중력 향상을 유도 |
| **대상 사용자** | 학생, 직장인 (장시간 집중이 필요한 사용자)                                                                   |
| **마감일**      | **2026년 4월 23일 (목)**                                                                                     |

### 확정 운영 기준

| 항목            | 확정값                              |
| --------------- | ----------------------------------- |
| 방 최대 인원    | 6명                                 |
| 영상 품질(메인) | 480p, 15fps                         |
| 영상 품질(서브) | 240p, 10fps                         |
| 화면 레이아웃   | 메인 사용자 1명 + 나머지 소형 화면  |
| 오디오          | 사용자별 ON/OFF 토글 제공           |
| 1차 전송 방식   | JPEG 프레임 브로드캐스트(Socket.IO) |
| 네트워크 범위   | 로컬 네트워크 전용                  |
| 구현 1순위      | 실시간 단체 영상 기능               |

### 팀 구성 (4인)

| 역할        | 인원 | 담당 업무                                                             |
| ----------- | ---- | --------------------------------------------------------------------- |
| **AI 모델** | 2명  | YOLOv8 TFLite 모델 학습·변환, MediaPipe 기반 시선/졸음 분석 모델 제공 |
| **앱 개발** | 2명  | 라즈베리파이 클라이언트 GUI, 서버 통신, 펫 시스템, FastAPI 서버 구축  |

## 1. 기술 스택 (Tech Stack)

| 구분                | 기술                          | 비고                                          |
| ------------------- | ----------------------------- | --------------------------------------------- |
| **환경 (Client)**   | **Raspberry Pi OS (64-bit)**  | 라즈베리파이 5 (앱 구동용)                    |
| **환경 (Server)**   | **Windows / Linux Laptop**    | FastAPI 서버 호스팅용                         |
| **언어**            | Python 3.10+                  | 클라이언트 및 서버 공통                       |
| **GUI**             | **PySide6 (Qt)**              | 라즈베리파이 데스크톱 UI                      |
| **카메라 입력**     | USB 웹캠 (UVC) + OpenCV       | 라즈베리파이에 직접 연결하여 캡처             |
| **영상 전송 (1차)** | JPEG 브로드캐스트 + Socket.IO | 빠른 PoC 구현 및 로컬망 실시간 단체 영상 확인 |
| **영상 전송 (2차)** | WebRTC (aiortc) + Socket.IO   | 지연/대역폭 최적화 전환용                     |
| **AI 비전**         | MediaPipe (Lite)              | 라즈베리파이용 시선/졸음 추적                 |
| **객체 탐지**       | YOLOv8-tiny (TFLite)          | **(타 팀원 제공 모델 사용)**                  |
| **서버/통신**       | FastAPI + Socket.io           | 노트북에서 구동, 실시간 데이터 중계           |
| **저장소**          | SQLite                        | 로컬(라즈베리파이) 및 서버 데이터 저장        |

> **참고:** AI 모델은 TFLite 형식(`.tflite`)으로 제작되어, 라즈베리파이에서 효율적으로 구동될 수 있도록 최적화되어 있습니다.

## 2. 시스템 구조 (System Architecture)

1. **라즈베리파이 클라이언트 (App):**
    - **AI 분석:** 라즈베리파이에 연결된 USB 웹캠 영상으로 사용자의 집중 상태(시선, 졸음, 핸드폰 사용)를 실시간 분석.
    - **디지털 펫 UI:** 분석 결과에 따라 캐릭터 애니메이션 재생 및 포인트 표시.
    - **통신:** 분석 상태 데이터와 JPEG 영상 프레임을 Socket.IO로 전송하고, 같은 방 참여자 영상/상태를 실시간 수신.
2. **노트북 서버 (Central Server):**
    - **방 관리:** 참여 코드를 통한 그룹 생성 및 유저 매칭.
    - **데이터 브로드캐스팅:** 특정 유저의 상태 변화와 JPEG 프레임을 같은 방의 모든 유저에게 즉시 전달.
    - **운영 제한:** 1개 room 최대 6명 제한, 로컬망 전용 운영.
    - **중앙 제어:** 세션 종료 시 최종 데이터 정산.

## 3. 핵심 기능 구현 전략

### A. AI 집중력 분석 (RPi Optimized)

- **웹캠 입력 고정:** 라즈베리파이 USB 웹캠(UVC)을 기본 입력 장치로 사용.
- **MediaPipe 적용:** 라즈베리파이 부하를 줄이기 위해 가벼운 설정을 사용하며, 프레임 스킵을 통해 발열 관리.
- **모델 통합:** 다른 팀원이 제공하는 TFLite 형식의 YOLOv8 모델을 OpenCV/TFLite 런타임으로 로드하여 핸드폰 탐지 수행.

### B. 디지털 펫 & 보상

- **캐릭터 애니메이션:** PySide6의 `QMovie`를 이용해 상태별(Idle, Sad, Angry, Sleep) GIF/시퀀스 이미지 출력.
- **성장/강등 로직:** 집중도 포인트에 따라 캐릭터의 단계를 결정하고 이를 로컬 DB에 영구 저장.

#### 캐릭터 성장 단계 (안)

| 단계 | 이름      | 필요 포인트 | 설명                              |
| ---- | --------- | ----------- | --------------------------------- |
| 1    | 🥚 알     | 0           | 초기 상태, 첫 시작                |
| 2    | 🐣 아기   | 100         | 알에서 부화, 기본 감정 표현       |
| 3    | 🐥 성장기 | 500         | 다양한 감정 표현 및 반응          |
| 4    | 🐔 성체   | 1500        | 최종 성장 단계, 풍부한 애니메이션 |

> **강등 조건:** 하루 평균 집중률이 30% 미만으로 3일 연속 유지될 경우 한 단계 강등.

### C. 랭킹/리더보드

- **그룹 내 랭킹:** 같은 방에 참여한 그룹원들의 일간/주간 집중 시간 및 포인트 순위 표시.
- **랭킹 데이터:** 서버에서 집계하며, 세션 종료 시 최종 데이터를 기반으로 갱신.
- **UI:** 클라이언트 앱 내 별도 랭킹 탭 또는 세션 종료 시 결과 화면에 표시.

### D. 실시간 그룹 연동

- **참여 코드 입장:** 사용자가 참여 코드를 입력하면 노트북 서버의 해당 Room에 접속.
- **실시간 동기화:** 내 집중 상태가 변할 때만 서버에 이벤트를 보내 네트워크 부하 최소화.

### E. 단체방 실시간 영상 보기 (1차: JPEG 브로드캐스트)

- **room 제한:** 최대 6명.
- **전송 방식:** 각 클라이언트는 JPEG 인코딩 프레임을 Socket.IO로 송신하고, 서버가 같은 room 참여자에게 브로드캐스트.
- **품질 정책:** 메인 화면 480p 15fps, 서브 화면 240p 10fps.
- **레이아웃 정책:** 메인 사용자 1명 + 나머지 소형 화면.
- **오디오 정책:** 사용자별 ON/OFF 토글 제공. (1차는 토글 상태 동기화 중심)
- **네트워크 범위:** 로컬 네트워크 환경만 지원.

## 4. 개발 단계 (Roadmap)

> **최종 마감: 2026년 4월 23일 (목)**

### Phase 1: 실시간 단체 영상 1차 (4/15 ~ 4/17)

- JPEG 브로드캐스트 기반 room 영상 송수신 구현 (최대 6명).
- 메인/서브 품질 정책(480p 15fps / 240p 10fps) 적용.
- 메인 1 + 소형 N 레이아웃 구현 및 오디오 ON/OFF 토글 UI 추가.

### Phase 2: 클라이언트 AI 엔진 (4/17 ~ 4/19)

- 라즈베리파이 USB 웹캠 연동 및 MediaPipe 기반 시선/졸음 분석 로직 구현.
- 타 팀원이 제공한 TFLite 모델 테스트 및 통합.

### Phase 3: 클라이언트 GUI 및 캐릭터 (4/19 ~ 4/20)

- PySide6를 이용한 라즈베리파이 전용 앱 창 및 캐릭터 애니메이션 시스템 구현.
- 타이머, 포인트 시스템, 캐릭터 성장/강등 로직 완성.

### Phase 4: 노트북 서버 연동 (4/20 ~ 4/22)

- 노트북에서 FastAPI + Socket.io 서버 구축.
- 라즈베리파이와 노트북 서버 간의 소켓 통신(상태 공유) 및 참여 코드 기능 연동.
- room 관리/랭킹 API 연동 및 영상/상태 이벤트 안정화.
- 랭킹/리더보드 API 및 UI 구현.
- 사전 통신 검증(PoC) 완료: `join_room`, `status_update` 이벤트 송수신 확인.

### Phase 5: 통합 및 연출 강화 (4/22 ~ 4/23)

- 졸음 감지 시 캐릭터가 깨워주는 효과(사운드/시각 연출) 추가.
- 라즈베리파이-노트북 간 실시간 통신 안정성 및 지연 시간(Latency) 최적화.
- 단체방 실시간 영상 최적화(FPS, 해상도, 압축률, 지연) 및 안정성 테스트.
- 전체 통합 테스트 및 버그 수정.

## 5. 데이터베이스 스키마 (SQLite)

### 클라이언트 DB (라즈베리파이 로컬)

```sql
-- 사용자 정보
CREATE TABLE user (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname    TEXT    NOT NULL,
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- 디지털 펫 상태
CREATE TABLE pet (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES user(id),
    stage       INTEGER DEFAULT 1,      -- 1:알, 2:아기, 3:성장기, 4:성체
    total_point INTEGER DEFAULT 0,
    updated_at  TEXT    DEFAULT (datetime('now'))
);

-- 세션별 집중 기록
CREATE TABLE focus_session (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES user(id),
    room_code       TEXT,
    start_time      TEXT    NOT NULL,
    end_time        TEXT,
    focus_seconds   INTEGER DEFAULT 0,
    unfocus_seconds INTEGER DEFAULT 0,
    earned_point    INTEGER DEFAULT 0
);
```

### 서버 DB (노트북)

```sql
-- 방 관리
CREATE TABLE room (
    code        TEXT    PRIMARY KEY,
    created_at  TEXT    DEFAULT (datetime('now')),
    is_active   INTEGER DEFAULT 1
);

-- 방 참여자
CREATE TABLE room_member (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    room_code   TEXT    NOT NULL REFERENCES room(code),
    nickname    TEXT    NOT NULL,
    joined_at   TEXT    DEFAULT (datetime('now'))
);

-- 랭킹 기록
CREATE TABLE ranking (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    room_code       TEXT    NOT NULL REFERENCES room(code),
    nickname        TEXT    NOT NULL,
    total_focus_sec INTEGER DEFAULT 0,
    total_point     INTEGER DEFAULT 0,
    recorded_at     TEXT    DEFAULT (datetime('now'))
);
```

## 6. 서버 API 명세

### REST API (FastAPI)

| Method | Endpoint                | 설명                       |
| ------ | ----------------------- | -------------------------- |
| `POST` | `/rooms`                | 새 방 생성, 참여 코드 반환 |
| `POST` | `/rooms/{code}/join`    | 참여 코드로 방 입장        |
| `GET`  | `/rooms/{code}/members` | 방 참여자 목록 조회        |    |
| `POST` | `/rooms/{code}/end`     | 세션 종료 및 최종 정산     |

### Socket.io 이벤트

| 방향            | 이벤트명        | 데이터                                              | 설명                         |
| --------------- | --------------- | --------------------------------------------------- | ---------------------------- |
| Client → Server | `join_room`     | `{ room_code, nickname }`                           | 방 입장                      |
| Client → Server | `status_update` | `{ nickname, state, timestamp }`                    | 집중 상태 변경 시 전송       |
| Client → Server | `video_frame`   | `{ room_code, nickname, jpeg_base64, ts, is_main }` | JPEG 영상 프레임 전송        |
| Client → Server | `audio_toggle`  | `{ room_code, nickname, audio_on }`                 | 오디오 ON/OFF 상태 전송      |
| Server → Client | `member_status` | `{ nickname, state, timestamp }`                    | 그룹원 상태 브로드캐스트     |
| Server → Client | `member_joined` | `{ nickname }`                                      | 새 멤버 입장 알림            |
| Server → Client | `room_video`    | `{ nickname, jpeg_base64, ts, is_main }`            | 그룹원 영상 프레임 수신      |
| Server → Client | `audio_changed` | `{ nickname, audio_on }`                            | 그룹원 오디오 상태 변경 알림 |
| Server → Client | `session_ended` | `{ ranking[] }`                                     | 세션 종료 및 최종 랭킹 전달  |

## 7. 구현 우선순위 재정의

1. 실시간 단체 영상(JPEG 브로드캐스트) 기능을 최우선 구현한다.
2. room 최대 인원 6명 기준으로 영상/상태 동기화를 먼저 안정화한다.
3. 메인 480p 15fps, 서브 240p 10fps 정책을 초기 릴리스 품질 기준으로 고정한다.
4. 오디오 ON/OFF 토글 기능을 UI와 이벤트에 먼저 반영한다.
5. 로컬 네트워크 환경에서 안정화 후, 필요 시 WebRTC 2차 전환을 검토한다.

> **state 값:** `focused`, `unfocused_gaze`, `drowsy`, `phone_detected`

## 8. 구현 현황 (2026-04-15)

### 완료된 구현 (1차)

- 서버: `join_room`, `status_update`, `video_frame`, `audio_toggle` 이벤트 구현 완료.
- 서버: room 최대 인원 6명 제한 로직 및 `join_failed` 응답 구현 완료.
- 서버: `room_video`, `audio_changed`, `member_list`, `member_left` 브로드캐스트 구현 완료.
- 클라이언트 테스트: 영상 프레임 송신 루프(`--send-video`, `--fps`, `--duration`) 및 오디오 토글(`--audio-on`) 지원 추가.

### 완료된 구현 (2차, 2026-04-15)

- 클라이언트 테스트: `--use-camera` 사용 시 OpenCV 실제 웹캠 프레임(JPEG) 송신 경로를 기본 송신 경로로 반영.
- 클라이언트 테스트: 메인/서브 품질 정책을 캡처 파이프라인 기본값으로 반영.
    - `--is-main` 기본: `640x480 @ 15fps`
    - 서브 기본: `320x240 @ 10fps`
    - `--fps`, `--frame-width`, `--frame-height` 지정 시 정책값 오버라이드 지원.

### 검증 결과

- **양방향 영상 이벤트 검증 성공:** 두 클라이언트 동시 접속 시 상호 `room_video` 수신 확인.
- **오디오 토글 이벤트 검증 성공:** `audio_toggle` 전송 시 `audio_changed` 수신 확인.
- **인원 제한 검증 성공:** 동일 room 7명 동시 접속 테스트에서 7번째 클라이언트 `join_failed(room_full)` 확인.

### 현재 테스트 파일

- `backend/server.py`: Socket.IO 이벤트 서버
- `frontend/client_test.py`: 다중 사용자 이벤트 테스트 클라이언트

### 다음 구현 항목

1. PySide6 화면에 메인 1 + 소형 N 레이아웃 렌더링 연결
2. Socket.IO 뷰어(`frontend/viewer_client.py`)와 PySide6 UI를 통합하여 앱 내부에서 영상 타일 표시
3. 실제 RPi 환경에서 FPS/해상도/지연 측정 후 품질 정책 미세 조정
