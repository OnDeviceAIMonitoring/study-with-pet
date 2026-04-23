# AI 탐지 알고리즘 상세 설명

> 이 문서는 **Study With Pet** 프로젝트의 전체 AI 탐지 알고리즘을 정리한 것입니다.  
> 코드 기준: `detectors/` 폴더 (`off_task.py`, `drowsiness.py`, `fidget.py`, `heart.py`, `shared.py`), `config/off_task.json`

---

## 목차

1. [사용 기술 개요](#1-사용-기술-개요)
   - 1.1 MediaPipe Holistic
   - 1.2 YOLOv11 (YOLO ONNX)
2. [시스템 전체 파이프라인](#2-시스템-전체-파이프라인)
3. [캘리브레이션 (Calibration)](#3-캘리브레이션-calibration)
4. [딴 짓 탐지 알고리즘 상세 (OffTaskDetector)](#4-딴-짓-탐지-알고리즘-상세-offtaskdetector)
   - 4.1 고개(시선) 방향 이탈 탐지 (Head Yaw Detection)
   - 4.2 객체(방해요소) 탐지 (Object/Phone Detection)
   - 4.3 웃으면서 말하는 행동 탐지 (Smile-Talking Detection)
   - 4.4 얼굴 트래커 화면 이탈 탐지 (Face Tracker Out-of-Screen)
   - 4.5 손 가시성 탐지 (Hand Visibility Detection)
5. [최종 집중 판단 로직 (Off-Task)](#5-최종-집중-판단-로직-off-task)
6. [졸음 탐지 알고리즘 (DrowsinessDetector)](#6-졸음-탐지-알고리즘-drowsinessdetector)
7. [산만함 탐지 알고리즘 (FidgetDetector)](#7-산만함-탐지-알고리즘-fidgetdetector)
8. [하트 제스처 감지 (HeartDetector)](#8-하트-제스처-감지-heartdetector)
9. [YOLO 파인튜닝 & PTQ INT8 양자화](#9-yolo-파인튜닝--ptq-int8-양자화)

---

## 1. 사용 기술 개요

### 1.1 MediaPipe Holistic

#### 개요

MediaPipe Holistic은 Google이 개발한 실시간 ML 파이프라인으로, 단일 프레임으로부터 **Face Mesh (468/478 포인트)**, **Pose (33 키포인트)**, **Hand (21 키포인트 × 좌/우)** 를 동시에 추론합니다.

#### Input / Output

| 구분 | 설명 |
|------|------|
| **Input** | RGB 이미지 (임의 해상도, 내부적으로 리사이즈) |
| **Output — Face Mesh** | 468개 (refine 시 478개) 3D 랜드마크 $(x, y, z)$, 정규화 좌표 $[0,1]$ |
| **Output — Pose** | 33개 키포인트 $(x, y, z, \text{visibility})$ |
| **Output — Hands** | 좌/우 각 21개 키포인트 $(x, y, z)$ |

#### 동작 원리

1. **Detection Stage**: 첫 프레임 또는 트래킹 실패 시, 경량 detector로 사람(얼굴/몸)의 ROI를 탐지
2. **Tracking Stage**: 이전 프레임의 랜드마크를 기반으로 ROI를 예측하고, 해당 영역만 크롭하여 각 서브모델 추론
3. **서브모델 통합**: Face Mesh, Pose, Hand 모델이 각각 독립적으로 추론되나, Holistic 파이프라인 내에서 한 번의 호출로 통합 실행

#### 본 프로젝트에서의 활용 (`SharedMediaPipe`)

```
SharedMediaPipe.process(rgb)  →  Holistic 1회 추론
    ├── face_landmarks   → Yaw 계산, 입 비율 계산, 얼굴 위치 추출
    ├── pose_landmarks   → 손목 가시성, 얼굴 fallback 추적
    ├── left_hand / right_hand  → 손 가시성, 객체 접촉 판정
```

모든 Detector(OffTask, Drowsiness, Fidget, Heart)가 **동일한 `SharedMediaPipe` 인스턴스**를 공유하여 프레임당 **단 1회**만 추론합니다.

---

### 1.2 YOLOv11 (YOLO26n.onnx)

#### 개요

YOLO (You Only Look Once)는 단일 패스로 객체의 **위치(Bounding Box)**와 **클래스(Class)**를 동시에 예측하는 실시간 객체 탐지 모델입니다. 본 프로젝트에서는 Ultralytics의 **YOLOv11 Nano** 변형을 ONNX 형식으로 변환하여 사용합니다.

#### Input / Output

| 구분 | 설명 |
|------|------|
| **Input** | $1 \times 3 \times H \times W$ 텐서 (기본 $640 \times 640$), RGB, $[0, 1]$ 정규화 |
| **Output** | $[N, 6]$ 또는 $[C, N]$ 형태의 탐지 결과 — $(x_1, y_1, x_2, y_2, \text{score}, \text{class\_id})$ |

#### 동작 원리

1. **Backbone**: 입력 이미지로부터 다중 스케일 특징 맵을 추출
2. **Neck (FPN/PAN)**: 다양한 해상도의 특징을 융합하여 작은 객체와 큰 객체 모두 탐지
3. **Head**: 각 그리드 셀에서 Bounding Box 좌표, Objectness Score, Class Probability를 예측
4. **NMS (Non-Maximum Suppression)**: 중복 탐지를 제거하여 최종 결과 출력

#### 전처리 파이프라인

$$
\text{frame}_{BGR} \xrightarrow{\text{resize}} (W_{in}, H_{in}) \xrightarrow{\text{BGR→RGB}} \xrightarrow{\text{HWC→CHW}} \xrightarrow{\div 255} \text{tensor}_{[1,3,H,W]}
$$

#### 후처리 — NMS

IoU (Intersection over Union) 기반 중복 제거:

$$
\text{IoU}(A, B) = \frac{|A \cap B|}{|A \cup B|}
$$

IoU가 임계값(기본 0.45) 이상인 중복 박스 중 점수가 낮은 것을 제거합니다.

#### 본 프로젝트에서의 활용

- **기본 모델 (`yolo26n.onnx`)**: COCO 사전학습, 28개 클래스 탐지
- **파인튜닝 모델 (`best_fine_tune_freeze.onnx`)**: 공부 환경 특화, 4개 클래스 (bottle, cup, cell phone, toothbrush)
- **Score Threshold**: 0.3 (config 설정)
- **비동기 실행**: `ThreadPoolExecutor`로 YOLO 추론을 별도 스레드에서 실행 → 메인 루프 블로킹 방지
- **추론 간격**: `phone_detect_every_n_frames` (기본 1프레임마다)

---

## 2. 시스템 전체 파이프라인

### 매 프레임 처리 흐름

```
웹캠 프레임 (BGR)
    │
    ▼
┌─────────────────────────────────┐
│  SharedMediaPipe.process(rgb)   │   ← Holistic 1회 추론
│  → face, pose, hands 랜드마크    │
└──────────────┬──────────────────┘
               │
    ┌──────────┼──────────────────────────┐
    ▼          ▼                          ▼
┌────────┐ ┌──────────┐           ┌──────────────┐
│Drows.. │ │Fidget    │           │  OffTask     │
│Detect  │ │Detector  │           │  Detector    │
└────────┘ └──────────┘           └──────┬───────┘
                                         │
                          ┌──────────────┼───────────────────┐
                          │              │                   │
                    ┌─────▼─────┐ ┌──────▼──────┐    ┌──────▼──────┐
                    │ YOLO ONNX │ │  MediaPipe  │    │   Kalman    │
                    │ Detection │ │   Landmark  │    │  Tracker    │
                    └─────┬─────┘ └──────┬──────┘    └──────┬──────┘
                          │              │                   │
                    ┌─────▼─────┐ ┌──────▼──────┐    ┌──────▼──────┐
                    │ (핸드폰)   │ │ Yaw 이탈    │    │ 화면 이탈     │
                    │ 방해요소   │ │ Smile-Talk  │    │ 판정         │
                    └─────┬─────┘ └──────┬──────┘    └──────┬──────┘
                          │              │                   │
                          └──────────────┼───────────────────┘
                                         ▼
                                 ┌───────────────┐
                                 │  최종 판단     │
                                 │ CONCENTRATING │
                                 │ vs DISTRACTED │
                                 └───────┬───────┘
                                         ▼
                                   Signal 발생
                                  (OFF_TASK 등)
```

---

## 3. 캘리브레이션 (Calibration)

### 목적

사용자의 **정상 자세**를 학습하여, 이후 탐지 정확도를 향상시킵니다.

### 흐름

```
앱 시작
    │
    ▼
캘리브레이션 시작 (duration_seconds = 5초)
    │
    ├── 매 프레임마다 수집:
    │     ├── 얼굴 중심 X 좌표 (tracker용)
    │     ├── MediaPipe Yaw 값 (시선 기준점)
    │     └── mouth_open_ratio (입 열림 baseline)
    │          └── mouth_open_ignore_above (0.18) 이상이면 무시 (하품/말하기 배제)
    │
    ▼
충분한 샘플 수집 (min_samples ≥ 20) && 시간 경과 (≥ 5초)
    │
    ▼
캘리브레이션 완료:
    ├── yaw_calib = median(yaw_samples)      ← 정면 기준 Yaw 값
    └── mouth_open_calib = median(mouth_open_samples)  ← 입 닫힌 상태 baseline
```

### 수식

$$
\text{yaw\_calib} = \text{median}(\{y_1, y_2, \dots, y_n\})
$$

$$
\text{mouth\_open\_calib} = \text{median}(\{m_i \mid m_i < \tau_{\text{ignore}}\})
$$

여기서 $\tau_{\text{ignore}} = 0.18$ (하품/말하기 시의 큰 값은 제외)

---

## 4. 딴 짓 탐지 알고리즘 상세 (OffTaskDetector)

### 4.1 고개(시선) 방향 이탈 탐지 (Head Yaw Detection)

#### 개요

MediaPipe Face Mesh의 코(nose)와 양쪽 눈 외곽 랜드마크의 상대적 위치 관계를 이용해 **좌우 고개 회전(Yaw)** 을 추정하고, 정면 기준으로부터 일정 각도 이상 벗어난 시간의 비율이 임계값을 초과하면 딴 짓으로 판정합니다.

#### 사용 랜드마크

| 랜드마크 | Face Mesh Index | 역할 |
|----------|----------------|------|
| 코끝 (Nose Tip) | 1 | Yaw 판별 기준점 |
| 왼쪽 눈 외곽 | 33 | 눈 간 거리 좌측 기준 |
| 오른쪽 눈 외곽 | 263 | 눈 간 거리 우측 기준 |

#### 알고리즘 순서도

```
Face Mesh 랜드마크 취득
    │
    ▼
Yaw 값 계산
    │  nose_x = landmark[1].x
    │  eye_center_x = (landmark[33].x + landmark[263].x) / 2
    │  eye_width = |landmark[263].x - landmark[33].x|
    │  yaw = (nose_x - eye_center_x) / eye_width
    │
    ▼
캘리브레이션 보정
    │  yaw_from_calib = yaw - yaw_calib
    │  yaw_degrees = yaw_from_calib × 90°
    │
    ▼
이탈 판정
    │  |yaw_degrees| > yaw_max_degrees (30°) ?
    │
    ├── Yes → yaw_event = 1 (이탈)
    └── No  → yaw_event = 0 (정상)
    │
    ▼
슬라이딩 윈도우 비율 계산
    │  window = 최근 5초간의 yaw_events
    │  yaw_ratio = count(event=1) / count(total)
    │
    ▼
Alert 판정
    │  yaw_ratio ≥ yaw_alert_ratio (0.3) ?
    │
    ├── Yes → status_yaw_out = True (딴 짓)
    └── No  → status_yaw_out = False
```

#### 핵심 수식

**1. Yaw 추정 (정규화된 비율)**

$$
\text{eye\_center}_x = \frac{x_{\text{left\_eye}} + x_{\text{right\_eye}}}{2}
$$

$$
\text{eye\_width} = |x_{\text{right\_eye}} - x_{\text{left\_eye}}|
$$

$$
\text{Yaw}_{\text{raw}} = \frac{x_{\text{nose}} - \text{eye\_center}_x}{\text{eye\_width}}
$$

이 값은 정면일 때 ≈ 0이며, 고개를 좌/우로 돌리면 음수/양수가 됩니다.  
눈 간 거리로 정규화하여 **카메라 거리에 독립적**입니다.

**2. 캘리브레이션 보정**

$$
\text{Yaw}_{\text{calib}} = \text{Yaw}_{\text{raw}} - \text{Yaw}_{\text{baseline}}
$$

$$
\text{Yaw}_{\text{deg}} = \text{Yaw}_{\text{calib}} \times 90°
$$

**3. 슬라이딩 윈도우 비율 판정**

$$
\text{yaw\_ratio} = \frac{\sum_{i \in W} \mathbb{1}[|\text{Yaw}_{\text{deg},i}| > \theta_{\text{max}}]}{|W|}
$$

여기서 $W$는 최근 $T_{\text{window}}$ 초(기본 5초)의 이벤트 집합, $\theta_{\text{max}} = 30°$

$$
\text{yaw\_alert} = \begin{cases} \text{True} & \text{if } \text{yaw\_ratio} \geq \alpha_{\text{yaw}} \\ \text{False} & \text{otherwise} \end{cases}
$$

여기서 $\alpha_{\text{yaw}} = 0.3$ (전체 윈도우의 30% 이상 이탈 시 경고)

#### 설계 의도

- **단일 프레임이 아닌 시간 비율 기반 판정**: 고개를 잠깐 돌리는 것은 자연스러운 행동이므로, 일정 시간 동안 지속적으로 이탈해야만 딴 짓으로 판정
- **캘리브레이션 보정**: 카메라 위치나 사용자의 자연스러운 정면 각도가 다를 수 있으므로 초기 3~5초의 중앙값을 기준으로 보정

---

### 4.2 객체(방해요소) 탐지 (Object/Phone Detection)

#### 개요

YOLO26n ONNX 모델로 웹캠 프레임에서 공부를 방해하는 객체(핸드폰, 리모컨, 장난감 등)를 탐지하고, MediaPipe 손 랜드마크와의 거리를 계산하여 **실제로 손에 쥐고 있는 경우에만** 방해요소로 판정합니다.

#### 탐지 대상 클래스 (28개)

**기본 모델 (28개):** 핸드폰(cell phone), 리모컨(remote), 가위(scissors), 포크(fork), 칼(knife), 스푼(spoon), 그릇(bowl), 새(bird), 고양이(cat), 개(dog), 프리스비(frisbee), 스키(skis), 스노보드(snowboard), 스포츠 공(sports ball), 연(kite), 야구 배트(baseball bat), 야구 글러브(baseball glove), 스케이트보드(skateboard), 서핑보드(surfboard), 테니스 라켓(tennis racket), 핫도그(hot dog), 피자(pizza), 도넛(donut), 소파(couch), 화분(potted plant), 테디베어(teddy bear), 헤어드라이기(hair drier), 칫솔(toothbrush)

**파인튜닝 모델 (4개, 권장):** bottle, cup, cell phone, toothbrush

#### 알고리즘 순서도

```
웹캠 프레임 (BGR)
    │
    ▼
전처리 (Preprocessing)
    │  resize → (640, 640)
    │  BGR → RGB → CHW → /255 → [1,3,640,640] float32
    │
    ▼
ONNX Runtime 추론 (비동기, ThreadPoolExecutor)
    │
    ▼
후처리 (Postprocessing)
    │  ├── 출력 형태에 따라 파싱 (Case A: [N,6], Case B: [C,N])
    │  ├── Score Threshold 필터링 (≥ 0.3)
    │  ├── 대상 Class ID 필터링 (28개 클래스)
    │  ├── 좌표 변환 (모델 좌표 → 원본 프레임 좌표)
    │  └── NMS (IoU threshold = 0.45)
    │
    ▼
손 접촉 필터 (Hand Contact Filter)
    │  MediaPipe Hand/Pose 랜드마크로 손 위치 수집
    │  각 탐지 박스와 손 사이 거리 계산
    │  distance ≤ max_distance (화면 5%) ?
    │
    ├── Yes → phone_detected = True
    └── No  → phone_detected = False (방해요소 아님)
    │
    ▼
슬라이딩 윈도우 비율 계산
    │  window = 최근 5초간의 phone_events
    │  phone_ratio = count(detected=1) / count(total)
    │
    ▼
Alert 판정
    │  phone_ratio ≥ phone_alert_ratio (0.3) ?
    │
    ├── Yes → phone_alert = True (딴 짓)
    └── No  → phone_alert = False
```

#### 핵심 수식

**1. 손-객체 거리 계산**

탐지된 바운딩 박스 $B = (x_1, y_1, x_2, y_2)$와 손 좌표 $(p_x, p_y)$의 최소 거리:

$$
d_x = \max(x_1 - p_x, \; 0, \; p_x - x_2)
$$

$$
d_y = \max(y_1 - p_y, \; 0, \; p_y - y_2)
$$

$$
d(p, B) = \sqrt{d_x^2 + d_y^2}
$$

박스 내부에 손이 있으면 $d = 0$

**2. 손 접촉 판정**

$$
\text{is\_held} = \exists \; p \in \text{HandPoints}, \; B \in \text{Boxes} : d(p, B) \leq \tau_{\text{dist}}
$$

여기서 $\tau_{\text{dist}} = 0.05 \times \max(W, H)$ (화면 크기의 5%)

**3. 슬라이딩 윈도우 비율 판정**

$$
\text{phone\_ratio} = \frac{\sum_{i \in W} \mathbb{1}[\text{detected}_i = 1]}{|W|}
$$

$$
\text{phone\_alert} = \begin{cases} \text{True} & \text{if } \text{phone\_ratio} \geq \alpha_{\text{phone}} \\ \text{False} & \text{otherwise} \end{cases}
$$

여기서 $\alpha_{\text{phone}} = 0.3$, $W$는 최근 5초간의 이벤트

#### 비동기 실행 구조

```
Main Thread                    YOLO Thread (ThreadPoolExecutor)
    │                                │
    ├── frame N: submit(frame) ──────▶ YOLO 추론 시작
    │   (이전 결과 사용)               │
    ├── frame N+1: 이전 결과 사용       │
    │                                │
    ├── frame N+k: future.done()? ◀──── 추론 완료
    │   결과 수집 + 새 frame submit     │
    │                                ▼
```

#### 하단 영역 필터링

손이 탐지되지 않은 경우, 화면 하단 80% 이하 영역의 객체는 무시합니다 (책상 위 물건 오탐 방지):

$$
\text{ignore} = \left(\frac{y_2}{H} \geq 0.8\right) \land (\text{no hand detected})
$$

---

### 4.3 웃으면서 말하는 행동 탐지 (Smile-Talking Detection)

#### 개요

웃으면서 동시에 말하는 행동을 탐지합니다. 단순히 입이 벌어진 것이 아니라, **시간적 리듬 분석(temporal rhythm)**을 통해 실제 대화 패턴을 식별하며, **하품(yawn) suppressor**로 오탐을 방지합니다.

#### 사용 랜드마크

| 랜드마크 | Face Mesh Index | 역할 |
|----------|----------------|------|
| 입 왼쪽 | 61 | 입 가로폭 좌측 |
| 입 오른쪽 | 291 | 입 가로폭 우측 |
| 입 윗입술 | 13 | 입 세로폭 상단 |
| 입 아랫입술 | 14 | 입 세로폭 하단 |
| 왼쪽 눈 외곽 | 33 | 정규화 기준 |
| 오른쪽 눈 외곽 | 263 | 정규화 기준 |

#### 알고리즘 순서도

```
Face Mesh 랜드마크 취득
    │
    ▼
특징 추출
    │  mouth_width_ratio = |mouth_R.x - mouth_L.x| / eye_width
    │  mouth_open_ratio  = |mouth_lower.y - mouth_upper.y| / eye_width
    │
    ▼
EMA 스무딩 & Baseline 보정
    │  mouth_open_ema = (1-α) × prev + α × current    (α = 0.35)
    │  mouth_open_rel = max(0, mouth_open_ema - mouth_open_calib)
    │
    ▼
시계열 수집 (슬라이딩 윈도우 1.5초)
    │  mouth_open_series = [(t₁, v₁), (t₂, v₂), ...]
    │  mouth_delta_series = [(t₁, Δ₁), (t₂, Δ₂), ...]
    │
    ▼
통계량 계산
    │  talk_stdev = std(open_vals)
    │  mean_open = mean(open_vals)
    │  max_open = max(open_vals)
    │  mean_delta = mean(delta_vals)
    │  peak_count = count_peaks(open_vals, prominence ≥ 0.008)
    │  active_ratio = count(v ≥ 0.035) / total
    │
    ▼
┌──────────────────────────────────────────────┐
│  3가지 상태 판별 (Smile / Talking / Yawn)     │
│                                              │
│  Smile:                                      │
│    mouth_width_ratio ≥ 0.42                  │
│                                              │
│  Talking:                                    │
│    0.035 ≤ mean_open ≤ 0.16                  │
│    AND mean_delta ≥ 0.006                    │
│    AND peak_count ≥ 2                        │
│    AND active_ratio ≥ 0.25                   │
│                                              │
│  Yawn:                                       │
│    max_open ≥ 0.18                           │
│    AND (peak_count ≤ 1 OR long_open ≥ 0.45) │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
최종 판정: Smile AND Talking AND NOT Yawn
    │
    ├── True  → status_smile_talking = True (딴 짓)
    └── False → status_smile_talking = False
```

#### 핵심 수식

**1. 특징 추출 (눈 간 거리로 정규화)**

$$
\text{mouth\_width\_ratio} = \frac{|x_{\text{mouth\_R}} - x_{\text{mouth\_L}}|}{|x_{\text{right\_eye}} - x_{\text{left\_eye}}|}
$$

$$
\text{mouth\_open\_ratio} = \frac{|y_{\text{lower}} - y_{\text{upper}}|}{|x_{\text{right\_eye}} - x_{\text{left\_eye}}|}
$$

눈 간 거리로 정규화하여 **카메라 거리에 무관**하게 비율을 계산합니다.

**2. EMA (Exponential Moving Average) 스무딩**

$$
\text{EMA}_t = (1 - \alpha) \cdot \text{EMA}_{t-1} + \alpha \cdot x_t, \quad \alpha = 0.35
$$

센서 노이즈와 프레임 간 떨림을 완화합니다.

**3. Baseline 보정**

$$
\text{mouth\_open\_rel} = \max(0, \; \text{EMA}_t - \text{baseline})
$$

캘리브레이션에서 수집한 baseline을 빼서 입을 다문 상태를 0에 가깝게 보정합니다.

**4. Peak 카운팅 (말하기 리듬 탐지)**

시계열 $\{v_1, v_2, \dots, v_n\}$에서 로컬 피크(local peak) 수를 셉니다:

$$
\text{peak at } i \iff v_i > v_{i-1} \;\land\; v_i > v_{i+1} \;\land\; \left(v_i - \min(v_{i-1}, v_{i+1})\right) \geq \tau_{\text{prom}}
$$

여기서 $\tau_{\text{prom}} = 0.008$ (최소 prominence)

대화 시에는 입의 열고 닫힘이 반복되어 **피크가 여러 번** 나타나지만, 하품은 **한 번 크게 벌어지고 유지**되므로 피크가 적습니다.

**5. Smile 판정**

$$
\text{is\_smile} = \text{mouth\_width\_ratio} \geq 0.42
$$

**6. Talking 판정 (다중 조건)**

$$
\text{is\_talking} = \begin{cases}
\text{True} & \text{if all conditions met:} \\
& 0.035 \leq \overline{m} \leq 0.16 \\
& \overline{\Delta} \geq 0.006 \\
& \text{peaks} \geq 2 \\
& r_{\text{active}} \geq 0.25
\end{cases}
$$

여기서:
- $\overline{m}$: 윈도우 내 mouth_open_rel 평균
- $\overline{\Delta}$: 프레임 간 변화량 평균
- $\text{peaks}$: 피크 카운트
- $r_{\text{active}} = \frac{|\{v_i \geq 0.035\}|}{N}$: 입이 열린 프레임 비율

**7. Yawn Suppressor**

$$
\text{is\_yawn} = \max(m) \geq 0.18 \;\land\; \left(\text{peaks} \leq 1 \;\lor\; r_{\text{long}} \geq 0.45\right)
$$

여기서 $r_{\text{long}} = \frac{|\{v_i \geq 0.18\}|}{N}$ (입이 크게 벌어진 프레임 비율)

**8. 최종 판정**

$$
\text{smile\_talking} = \text{is\_smile} \;\land\; \text{is\_talking} \;\land\; \lnot\;\text{is\_yawn}
$$

#### 설계 의도

- **단순 mouth open이 아닌 시간적 리듬 분석**: 하품, 심호흡 등과 실제 대화를 구별
- **Yawn Suppressor**: 크게 벌리고 오래 유지하는 패턴은 하품으로 분류하여 오탐 방지
- **EMA + Baseline Calibration**: 개인별 입 크기 차이와 센서 노이즈를 보정

---

### 4.4 얼굴 트래커 화면 이탈 탐지 (Face Tracker Out-of-Screen)

#### 개요

**Kalman Filter** 기반 얼굴 트래커로 얼굴 위치를 연속적으로 추적하고, 예측된 얼굴 중심이 화면(정규화 좌표 $[0,1]^2$) 밖으로 나가면 화면 이탈로 판정합니다. 얼굴이 일시적으로 미감지되어도 Kalman 예측으로 위치를 유지합니다.

#### Kalman Filter 설계

**상태 벡터** $\mathbf{x} = [c_x, c_y, v_x, v_y]^T$ (얼굴 중심 좌표 + 속도)

**상태 전이 행렬** ($dt$: 프레임 간격):

$$
\mathbf{F} = \begin{bmatrix} 1 & 0 & dt & 0 \\ 0 & 1 & 0 & dt \\ 0 & 0 & 1 & 0 \\ 0 & 0 & 0 & 1 \end{bmatrix}
$$

**측정 행렬** (위치만 관측 가능):

$$
\mathbf{H} = \begin{bmatrix} 1 & 0 & 0 & 0 \\ 0 & 1 & 0 & 0 \end{bmatrix}
$$

**프로세스 노이즈** $\mathbf{Q} = 10^{-3} \cdot \mathbf{I}_4$,  
**측정 노이즈** $\mathbf{R} = 10^{-2} \cdot \mathbf{I}_2$

#### 알고리즘 순서도

```
Face/Pose 랜드마크로 얼굴 측정 (measurement)
    │  ├── Face Mesh 있으면: 468개 랜드마크 → bbox, center, area
    │  └── Pose만 있으면: NOSE/EYE/EAR 5개 → bbox, center, area
    │
    ▼
트래커 초기화 여부 확인
    │
    ├── 미초기화 & 측정값 있음 → 초기화 (statePost = [cx, cy, 0, 0])
    │
    └── 초기화됨 →
         │
         ▼
    Kalman Predict
         │  pred_center = F × statePost
         │
         ▼
    측정값 매칭 (Gating)
         │  distance_ok = ||meas - pred|| ≤ 0.25
         │  area_ok = 0.6 ≤ area / size_ema ≤ 1.7
         │
         ├── Matched → Speed Limiter → Kalman Correct
         │     └── size_ema 업데이트 (α=0.2)
         │
         ├── Not Matched → 트래커 리셋 (새 위치로 재초기화)
         │
         └── 측정값 없음 → 예측값만 사용, lost_frames++
    │
    ▼
화면 이탈 판정
    │  center = tracked_center (정규화 좌표)
    │  is_out = (x < 0 OR x > 1 OR y < 0 OR y > 1)
    │
    ▼
지속 시간 판정
    │  tracker_out_counter (연속 프레임 수)
    │  ≥ tracker_out_seconds × fps (0.6초) ?
    │
    ├── Yes → status_tracker_out = True (딴 짓)
    └── No  → status_tracker_out = False
```

#### 핵심 수식

**1. Kalman Filter 예측 (Predict)**

$$
\hat{\mathbf{x}}_{k|k-1} = \mathbf{F} \cdot \hat{\mathbf{x}}_{k-1|k-1}
$$

$$
\mathbf{P}_{k|k-1} = \mathbf{F} \cdot \mathbf{P}_{k-1|k-1} \cdot \mathbf{F}^T + \mathbf{Q}
$$

**2. Kalman Filter 업데이트 (Correct)**

$$
\mathbf{K}_k = \mathbf{P}_{k|k-1} \cdot \mathbf{H}^T \cdot (\mathbf{H} \cdot \mathbf{P}_{k|k-1} \cdot \mathbf{H}^T + \mathbf{R})^{-1}
$$

$$
\hat{\mathbf{x}}_{k|k} = \hat{\mathbf{x}}_{k|k-1} + \mathbf{K}_k \cdot (\mathbf{z}_k - \mathbf{H} \cdot \hat{\mathbf{x}}_{k|k-1})
$$

$$
\mathbf{P}_{k|k} = (\mathbf{I} - \mathbf{K}_k \cdot \mathbf{H}) \cdot \mathbf{P}_{k|k-1}
$$

**3. 속도 제한 (Speed Limiter)**

측정값의 급격한 이동을 제한하여 오탐을 방지합니다:

$$
\mathbf{d} = \mathbf{p}_{\text{meas}} - \mathbf{p}_{\text{prev}}
$$

$$
d_{\text{max}} = v_{\text{max}} \cdot dt, \quad v_{\text{max}} = 2.5 \; \text{screen/sec}
$$

$$
\mathbf{p}_{\text{capped}} = \begin{cases} \mathbf{p}_{\text{meas}} & \text{if } \|\mathbf{d}\| \leq d_{\text{max}} \\ \mathbf{p}_{\text{prev}} + \frac{\mathbf{d}}{\|\mathbf{d}\|} \cdot d_{\text{max}} & \text{otherwise} \end{cases}
$$

**4. 면적 EMA (크기 변화 추적)**

$$
\text{size\_ema}_{t} = (1 - \alpha_s) \cdot \text{size\_ema}_{t-1} + \alpha_s \cdot A_t, \quad \alpha_s = 0.2
$$

**5. 매칭 게이팅 (Gating)**

$$
\text{matched} = \left(\|\mathbf{p}_{\text{meas}} - \mathbf{p}_{\text{pred}}\| \leq 0.25\right) \;\land\; \left(0.6 \leq \frac{A_{\text{meas}}}{\text{size\_ema}} \leq 1.7\right)
$$

**6. 화면 이탈 판정**

$$
\text{is\_out} = (c_x < 0) \;\lor\; (c_x > 1) \;\lor\; (c_y < 0) \;\lor\; (c_y > 1)
$$

$$
\text{tracker\_out} = \begin{cases} \text{True} & \text{if } \text{out\_counter} \geq \tau_{\text{out}} \times \text{fps} \\ \text{False} & \text{otherwise} \end{cases}
$$

여기서 $\tau_{\text{out}} = 0.6$ 초

#### 설계 의도

- **Kalman Filter**: 얼굴이 일시적으로 미감지되어도 예측 위치를 유지하여 연속적 추적 가능
- **Speed Limiter**: 다른 사람이 지나가거나 갑작스런 오탐에 의한 위치 점프 방지
- **면적 게이팅**: 얼굴 크기가 급격히 바뀌면 다른 사람으로 판단하고 리셋
- **Fallback (Pose)**: Face Mesh가 안 잡혀도 Pose의 코/눈/귀 랜드마크로 대략적 추적

---

### 4.5 손 가시성 탐지 (Hand Visibility Detection)

#### 개요

공부 중에는 손이 카메라에 보여야 합니다(키보드/마우스/필기구 사용). 손이 장시간 보이지 않거나 책상 위에 없으면 딴 짓으로 판정합니다. 또한 **공부 시작 감지**에도 활용됩니다.

#### 알고리즘 순서도

```
MediaPipe 결과 확인
    │
    ├── Hand Landmarks 존재?
    │    └── Yes → has_hand = True
    │
    ├── Pose Wrist Visibility > 0.35?
    │    └── Yes → has_hand = True
    │
    └── 둘 다 없음 → has_hand = False
    │
    ▼
공부 시작 감지
    │  처음으로 hand 감지 → study_started = True
    │
    ▼
손 부재 지속 시간 체크
    │  no_hand_counter (연속 미감지 프레임)
    │  ≥ no_hand_seconds × fps (0.8초) ?
    │
    ├── Yes → status_no_hands = True
    └── No  → status_no_hands = False
    │
    ▼
책상 위 손 위치 확인 (보조 판정)
    │  wrist.y > desk_y_threshold (0.6) ?
    │
    └── No → status_no_hands = True (손이 책상 위에 없음)
```

#### 핵심 수식

**1. 손 가시성 판정**

$$
\text{has\_hand} = (\text{left\_hand} \neq \varnothing) \;\lor\; (\text{right\_hand} \neq \varnothing) \;\lor\; \max(v_{\text{L\_wrist}}, v_{\text{R\_wrist}}) > 0.35
$$

**2. 책상 위 손 판정**

$$
\text{hands\_on\_desk} = (y_{\text{L\_wrist}} > \tau_{\text{desk}}) \;\lor\; (y_{\text{R\_wrist}} > \tau_{\text{desk}})
$$

여기서 $\tau_{\text{desk}} = 0.6$ (정규화 좌표에서 화면 하단 60% 이하)

---

## 5. 최종 집중 판단 로직 (Off-Task)

모든 개별 탐지 결과를 종합하여 **CONCENTRATING** vs **DISTRACTED** 를 결정합니다.

### 판정 수식

$$
\text{is\_concentrating} = \lnot\Big(
\underbrace{\lnot S}_{\text{미시작}} \;\lor\;
\underbrace{N_h}_{\text{손 없음}} \;\lor\;
\underbrace{P_a}_{\text{핸드폰}} \;\lor\;
\underbrace{T_o}_{\text{트래커 이탈}} \;\lor\;
\underbrace{F_m}_{\text{얼굴 미감지}} \;\lor\;
\underbrace{ST}_{\text{웃음+대화}} \;\lor\;
\underbrace{Y_o}_{\text{Yaw 이탈}}
\Big)
$$

| 기호 | 변수명 | 조건 |
|------|--------|------|
| $S$ | `study_started` | 손이 처음 감지되면 True |
| $N_h$ | `status_no_hands` | 손 부재 0.8초 이상 |
| $P_a$ | `phone_alert` | 객체 감지 비율 ≥ 30% (5초 윈도우) |
| $T_o$ | `status_tracker_out` | 얼굴 화면 밖 0.6초 이상 |
| $F_m$ | `status_face_missing` | 얼굴 미감지 1.2초 이상 |
| $ST$ | `status_smile_talking` | 웃으면서 대화 중 |
| $Y_o$ | `status_yaw_out` | 고개 이탈 비율 ≥ 30% (5초 윈도우) |

**하나라도 True이면 DISTRACTED**, 모두 False이면 CONCENTRATING입니다.

### Signal 생성

DISTRACTED 판정 시 `OFF_TASK` Signal이 발생하며, detail에 원인이 기록됩니다:

```
Signal(name="OFF_TASK", source="off_task", level=0.8, detail="phone, yaw_out")
```

---

## 6. 졸음 탐지 알고리즘 (DrowsinessDetector)

> 코드: `detectors/drowsiness.py`

### 개요

두 가지 경로로 졸음을 감지합니다:
- **경로 A (얼굴 보임)**: EAR(Eye Aspect Ratio) 기반 눈 감김 지속 판정
- **경로 B (얼굴 안 보임)**: Pose Pitch 기반 고개 숙임 지속 판정

### 사용 랜드마크

| 랜드마크 | Face Mesh Index | 역할 |
|----------|----------------|------|
| 왼쪽 눈 | 362, 385, 387, 263, 373, 380 | 좌안 EAR 계산 |
| 오른쪽 눈 | 33, 160, 158, 133, 153, 144 | 우안 EAR 계산 |
| 코끝 | 1 | Face Pitch 기준 |
| 턱 | 152 | Face Pitch 하단 |
| 이마 | 10 | Face Pitch 상단 |

### 알고리즘 순서도

```
프레임 입력
    │
    ├── Face Mesh 존재?
    │    │
    │    ├── Yes (경로 A):
    │    │    │
    │    │    ▼
    │    │  EAR 계산 (좌안 + 우안 평균)
    │    │    │
    │    │    ▼
    │    │  Face Pitch 계산 (코-이마-턱 비율)
    │    │    │
    │    │    ▼
    │    │  Adaptive Threshold 적용
    │    │    │  pitch < normal - 22° → Deep-down mode (낮은 임계값)
    │    │    │  그 외 → pitch 기반 보간 임계값
    │    │    │
    │    │    ▼
    │    │  EAR < threshold?
    │    │    ├── Yes → counter++
    │    │    │    └── counter ≥ 20 → DROWSINESS Signal
    │    │    └── No  → counter = 0
    │    │
    │    └── 캘리브레이션 미완료 시:
    │         50프레임 수집 → normal EAR/Pitch 설정
    │
    └── No (경로 B):
         │
         ▼
       사람이 화면 안에 있는지 확인
         │  (OffTask tracker_out / Pose 존재 여부)
         │
         ├── 화면 밖 → 졸음 판단 안 함
         └── 화면 안 →
              │
              ▼
            Pose Pitch < normal - 15° (또는 얼굴 미감지 2초)
              │  → 고개 숙임 판정
              │
              ▼
            3초 이상 지속 → DROWSINESS Signal
```

### 핵심 수식

**1. EAR (Eye Aspect Ratio)**

눈의 6개 랜드마크 $p_1, \dots, p_6$에 대해:

$$
\text{EAR} = \frac{\|p_2 - p_6\| + \|p_3 - p_5\|}{2 \cdot \|p_1 - p_4\|}
$$

양쪽 눈의 평균:

$$
\text{EAR}_{\text{avg}} = \frac{\text{EAR}_L + \text{EAR}_R}{2}
$$

눈을 뜬 상태에서 ≈ 0.25~0.35, 감으면 ≈ 0.05~0.15

**2. 캘리브레이션 (초기 50프레임)**

$$
\text{normal\_EAR} = \overline{\text{EAR}}_{\text{calib}}
$$

$$
\text{EAR\_thresh\_up} = \text{normal\_EAR} \times 0.40
$$

$$
\text{EAR\_thresh\_down} = \text{EAR\_thresh\_up} - 0.02
$$

**3. Face Pitch 추정**

$$
\text{face\_h} = y_{\text{chin}} - y_{\text{forehead}}
$$

$$
\text{ratio} = \frac{y_{\text{nose}} - \frac{y_{\text{forehead}} + y_{\text{chin}}}{2}}{\text{face\_h}}
$$

$$
\text{Pitch} = -\text{ratio} \times 90°
$$

**4. Adaptive EAR Threshold**

고개를 숙이면 EAR이 자연스럽게 낮아지므로, Pitch에 따라 임계값을 조정합니다:

$$
\text{EAR\_thresh}(\text{pitch}) = \begin{cases}
\text{thresh\_down} & \text{if pitch} \leq -15° \\
\text{thresh\_up} & \text{if pitch} \geq 10° \\
\text{thresh\_down} + t^2 \cdot (\text{thresh\_up} - \text{thresh\_down}) & \text{otherwise}
\end{cases}
$$

여기서 $t = \frac{\text{pitch} - (-15°)}{10° - (-15°)}$ (2차 보간)

Deep-down mode ($\text{pitch} < \text{normal} - 22°$)에서는 `thresh_up` 사용 (더 관대하게)

**5. 졸음 판정 조건**

$$
\text{경로 A: } \text{alarm} = (\text{counter} \geq 20) \quad (\text{EAR} < \text{thresh가 20프레임 연속})
$$

$$
\text{경로 B: } \text{head\_down\_drowsy} = (\text{head\_down 지속 시간} \geq 3\text{초})
$$

### 설계 의도

- **Adaptive Threshold**: 고개 숙여서 노트 필기 시 EAR이 자연스럽게 낮아지는 오탐 방지
- **Deep-down mode**: 극도로 고개 숙인 자세에서는 별도 기준 적용
- **경로 B (Pose fallback)**: Face Mesh가 안 잡혀도 Pose 키포인트로 고개 숙임 감지
- **OffTask 연동**: 사람이 화면 밖에 있을 때는 졸음 판단을 하지 않음

---

## 7. 산만함 탐지 알고리즘 (FidgetDetector)

> 코드: `detectors/fidget.py`

### 개요

상반신 키포인트(코, 양 어깨, 양 팔꿈치)의 프레임 간 이동량(에너지)을 추적하여, **반복적인 큰 움직임(burst)**이 일정 시간 내에 여러 번 발생하면 산만함(fidget)으로 판정합니다.

### 추적 키포인트

| Pose Index | 키포인트 |
|------------|----------|
| 0 | Nose (코) |
| 11 | Left Shoulder (왼쪽 어깨) |
| 12 | Right Shoulder (오른쪽 어깨) |
| 13 | Left Elbow (왼쪽 팔꿈치) |
| 14 | Right Elbow (오른쪽 팔꿈치) |

### 알고리즘 순서도

```
Pose 랜드마크 취득 (5개 키포인트)
    │
    ▼
에너지 계산 (이전 프레임 vs 현재 프레임)
    │  energy = mean(||curr_pts - prev_pts||)
    │
    ▼
캘리브레이션 (최초 5초)
    │  normal_energy = 3 (고정 기준)
    │
    ▼
스무딩 (0.8초 윈도우 평균)
    │  smooth = mean(energy_window)
    │  ratio = smooth / normal_energy
    │
    ▼
Burst 감지
    │  ratio > 5.0 (BURST_THRESH) ?
    │
    ├── Yes → burst 시작 (활성화)
    │
    └── burst 종료 시:
         │  지속 시간 ≥ 0.8초 ?
         │
         ├── Yes → burst_times에 기록
         │         + 쿨다운 1.5초
         └── No  → 무시
    │
    ▼
Burst 카운트 판정 (최근 30초 윈도우)
    │  burst_count ≥ 4 ?
    │
    ├── Yes → LOW_FOCUS Signal (산만함)
    └── No  → 정상
    │
    ▼
리셋: 마지막 burst로부터 15초 경과 → burst_times 초기화
```

### 핵심 수식

**1. 에너지 (프레임 간 이동량)**

$$
E_t = \frac{1}{N} \sum_{i=1}^{N} \|\mathbf{p}_{t,i} - \mathbf{p}_{t-1,i}\|_2
$$

여기서 $N = 5$ (추적 키포인트 수), $\mathbf{p}_{t,i}$는 $t$ 프레임에서 $i$번째 키포인트의 픽셀 좌표

**2. 스무딩 (이동 평균)**

$$
E_{\text{smooth}} = \frac{1}{|W|} \sum_{(t, e) \in W} e
$$

여기서 $W$는 최근 0.8초의 에너지 값 집합

**3. 에너지 비율**

$$
r = \frac{E_{\text{smooth}}}{E_{\text{normal}}}
$$

$E_{\text{normal}} = 3$ (고정 기준값)

**4. Burst 판정**

$$
\text{is\_burst} = (r > \tau_{\text{burst}}), \quad \tau_{\text{burst}} = 5.0
$$

**5. 산만함 판정**

$$
\text{fidget\_alert} = \left(\sum_{b \in B_{30s}} 1\right) \geq 4
$$

여기서 $B_{30s}$는 최근 30초 이내에 발생한, 0.8초 이상 지속된 burst 집합

### 설계 의도

- **에너지 기반**: 단순 위치가 아닌 프레임 간 이동량을 측정하여 실제 움직임 정도를 파악
- **Burst 패턴 분석**: 단발성 움직임은 무시하고, 반복적으로 큰 움직임이 나타나야 산만함으로 판정
- **쿨다운**: 연속된 움직임을 하나의 burst로 병합 (1.5초 간격)
- **자동 리셋**: 15초간 burst 없으면 카운트 초기화 → 일시적 산만함 후 집중 복귀 허용

---

## 8. 하트 제스처 감지 (HeartDetector)

> 코드: `detectors/heart.py`

### 개요

양손의 **검지 끝**과 **엄지 끝**이 서로 가까이 맞닿고, 검지가 구부러지며, 엄지가 아래로 교차하는 포즈를 감지하여 **큰 하트 제스처**를 인식합니다. Jitter 방지를 위한 히스토리 버퍼 기반 과반수 투표를 사용합니다.

### 사용 랜드마크

| Hand Landmark Index | 키포인트 | 역할 |
|---------------------|----------|------|
| 4 | Thumb Tip (엄지 끝) | 엄지 맞닿음 판정 |
| 3 | Thumb IP (엄지 IP 관절) | 엄지 교차 판정 |
| 5 | Index MCP (검지 MCP) | 검지 굽힘 각도 계산 |
| 6 | Index PIP (검지 PIP) | 검지 굽힘 각도 계산 |
| 8 | Index Tip (검지 끝) | 검지 맞닿음 + 굽힘 판정 |

### 알고리즘 순서도

```
양손 Hand Landmarks 취득
    │
    ├── 2개 미만 → 하트 아님
    │
    └── 2개 이상 →
         │
         ▼
    거리 계산
         │  dist_index = ||hand1[8] - hand2[8]||   (검지 끝 거리)
         │  dist_thumb = ||hand1[4] - hand2[4]||   (엄지 끝 거리)
         │
         ▼
    검지 굽힘 각도 계산
         │  angle_h1 = angle(h1[8], h1[6], h1[5])
         │  angle_h2 = angle(h2[8], h2[6], h2[5])
         │
         ▼
    엄지 교차 확인
         │  thumb_cross = (h1[4].y > h1[3].y) AND (h2[4].y > h2[3].y)
         │
         ▼
    3가지 조건 AND 판정
         │  ├── dist_index < 0.08 AND dist_thumb < 0.08
         │  ├── angle_h1 < 150° AND angle_h2 < 150°
         │  └── thumb_cross = True
         │
         ▼
    히스토리 버퍼 (7프레임) — 과반수 투표 (60%)
         │
         ├── 과반수 True → HEART Signal
         └── 그 외 → 하트 아님
```

### 핵심 수식

**1. 검지 끝 / 엄지 끝 거리** (정규화 좌표)

$$
d_{\text{index}} = \sqrt{(x^{(1)}_8 - x^{(2)}_8)^2 + (y^{(1)}_8 - y^{(2)}_8)^2}
$$

$$
d_{\text{thumb}} = \sqrt{(x^{(1)}_4 - x^{(2)}_4)^2 + (y^{(1)}_4 - y^{(2)}_4)^2}
$$

**2. 검지 굽힘 각도**

$$
\mathbf{v}_1 = \mathbf{p}_8 - \mathbf{p}_6, \quad \mathbf{v}_2 = \mathbf{p}_5 - \mathbf{p}_6
$$

$$
\theta = \arccos\left(\frac{\mathbf{v}_1 \cdot \mathbf{v}_2}{\|\mathbf{v}_1\| \cdot \|\mathbf{v}_2\|}\right)
$$

$\theta < 150°$이면 검지가 충분히 구부러진 상태

**3. 엄지 교차 조건**

$$
\text{thumb\_cross} = (y^{(1)}_4 > y^{(1)}_3) \;\land\; (y^{(2)}_4 > y^{(2)}_3)
$$

엄지 끝이 IP 관절보다 아래에 위치 → 엄지가 아래로 꺾인 하트 포즈

**4. 하트 감지 (단일 프레임)**

$$
\text{detected} = (d_{\text{index}} < 0.08) \;\land\; (d_{\text{thumb}} < 0.08) \;\land\; (\theta_1 < 150°) \;\land\; (\theta_2 < 150°) \;\land\; \text{thumb\_cross}
$$

**5. 히스토리 과반수 투표 (Jitter 방지)**

$$
\text{is\_heart} = \frac{\sum_{i=1}^{K} \mathbb{1}[\text{detected}_i]}{K} > 0.6, \quad K = 7
$$

최근 7프레임 중 60% 이상에서 하트로 판정되어야 최종 HEART Signal 발생

### 설계 의도

- **과반수 투표**: 손 랜드마크의 프레임 간 떨림(jitter)으로 인한 순간적 오탐/미탐 방지
- **다중 조건**: 단순 거리만이 아닌 각도 + 교차 조건을 함께 사용하여 정확도 향상
- **정규화 좌표 기반**: 카메라 거리에 무관하게 동작

---

## 9. YOLO 파인튜닝 & PTQ INT8 양자화

### 9.1 파인튜닝 (Fine-Tuning)

#### 목적

COCO 사전학습 모델을 기반으로, 공부 환경에서 자주 등장하는 방해요소에 대한 탐지 정확도를 향상시킵니다.

#### 접근

| 항목 | 내용 |
|------|------|
| **Base Model** | YOLOv11 Nano (COCO 사전학습) |
| **Fine-Tuning 전략** | Transfer Learning — Backbone Freeze |
| **학습 데이터** | COCO에서 4개 관심 클래스(bottle, cup, cell phone, toothbrush) 필터링 + 공부 환경 촬영 데이터 |
| **출력 형식** | ONNX (.onnx) — CPU 기반 크로스 플랫폼 추론 |

#### 학습 파이프라인

```
COCO Dataset (80 classes)
    │
    ▼
관심 클래스 4개 필터링
    │  (bottle, cup, cell phone, toothbrush)
    │
    ▼
YOLOv11n 사전학습 가중치 로드
    │
    ▼
Fine-Tuning (Transfer Learning — Backbone Freeze)
    │  ├── 데이터 증강: mosaic, mixup, flip, scale
    │  ├── Optimizer: SGD / AdamW
    │  └── Loss: CIOU + BCE (cls) + DFL
    │
    ▼
Best Checkpoint 선택 (mAP@0.5 기준)
    │
    ▼
ONNX Export
    │  model.export(format="onnx", imgsz=640)
    │
    ▼
best_fine_tune_freeze.onnx (파인튜닝 모델)
```

### 9.2 PTQ INT8 양자화 (Post-Training Quantization)

#### 목적

모델 가중치와 활성화를 FP32에서 INT8로 변환하여 **모델 크기 감소**(약 4배)와 **추론 속도 향상**을 달성합니다. 재학습 없이 기존 모델에 적용 가능합니다.

#### PTQ 원리

**양자화 공식 (Affine Quantization)**:

$$
x_q = \text{round}\left(\frac{x}{s}\right) + z
$$

$$
x \approx s \cdot (x_q - z)
$$

여기서:
- $x$: 원래 FP32 값
- $x_q$: 양자화된 INT8 값
- $s$: 스케일 팩터 (scale)
- $z$: 영점 오프셋 (zero point)

**스케일 팩터 결정**:

$$
s = \frac{x_{\max} - x_{\min}}{2^8 - 1} = \frac{x_{\max} - x_{\min}}{255}
$$

**영점 오프셋**:

$$
z = \text{round}\left(-\frac{x_{\min}}{s}\right)
$$

#### 캘리브레이션 (Calibration for PTQ)

PTQ에서는 대표 데이터셋(calibration dataset)을 모델에 통과시켜 각 레이어의 활성화 분포를 수집하고, 이를 기반으로 최적의 스케일/영점을 결정합니다.

```
학습된 FP32 ONNX 모델
    │
    ▼
Calibration Dataset 준비
    │  (학습 데이터의 일부, 보통 100~500장)
    │
    ▼
각 레이어 활성화 분포 수집
    │  ├── Min-Max 방식: 단순 최솟값/최댓값 사용
    │  ├── Percentile 방식: 이상치 제외 (99.99th percentile)
    │  └── Entropy 방식 (KL Divergence): FP32와 INT8 분포 간 정보 손실 최소화
    │
    ▼
레이어별 Scale / Zero-point 결정
    │
    ▼
INT8 양자화 적용
    │
    ▼
yolo26n_int8.onnx (양자화 모델)
```

#### FP32 vs INT8 비교

| 항목 | FP32 | INT8 (PTQ) |
|------|------|------------|
| **가중치 비트 수** | 32 bits | 8 bits |
| **모델 크기** | ~5.4 MB (Nano) | ~1.5 MB (약 3.6배 감소) |
| **추론 속도** | Baseline | ~1.5~3× 빠름 (하드웨어 의존) |
| **정확도** | Baseline | 약간 감소 (mAP -0.5~2% 이내) |
| **메모리 사용량** | 높음 | 약 4배 감소 |

#### 양자화 적용 시 고려사항

- **Calibration 데이터 품질**: 실제 사용 환경과 유사한 이미지를 사용해야 정확한 분포 추정 가능
- **Per-channel vs Per-tensor**: 채널별 양자화가 더 정확하나 연산 오버헤드 발생
- **Sensitive Layer 분석**: 양자화에 민감한 레이어는 FP32로 유지하는 Mixed Precision 전략 가능

---

## 부록: 설정 파라미터 요약 (`config/off_task.json`)

| 카테고리 | 파라미터 | 기본값 | 설명 |
|----------|----------|--------|------|
| **YOLO** | `phone_score_threshold` | 0.3 | 최소 탐지 신뢰도 |
| | `phone_requires_hand_contact` | true | 손 접촉 필터 활성화 |
| | `phone_detect_every_n_frames` | 1 | YOLO 추론 간격 (프레임) |
| **Yaw** | `yaw_max_degrees` | 30° | 최대 허용 고개 회전각 |
| | `yaw_window_seconds` | 5.0s | 슬라이딩 윈도우 크기 |
| | `yaw_alert_ratio` | 0.3 | Alert 판정 비율 |
| **Phone** | `phone_window_seconds` | 5.0s | 슬라이딩 윈도우 크기 |
| | `phone_alert_ratio` | 0.3 | Alert 판정 비율 |
| **Smile-Talk** | `smile_width_ratio_threshold` | 0.42 | 웃음 판정 가로폭 비율 |
| | `talking_open_ratio_min` | 0.035 | 말하기 최소 개구 비율 |
| | `talking_open_ratio_max` | 0.16 | 말하기 최대 개구 비율 |
| | `talking_delta_mean_threshold` | 0.006 | 프레임 간 변화량 최소 |
| | `talking_peak_count_threshold` | 2 | 최소 피크 수 |
| | `talking_active_ratio_threshold` | 0.25 | 활성 프레임 비율 |
| | `yawn_open_ratio_threshold` | 0.18 | 하품 판정 개구 비율 |
| | `smile_talk_window_seconds` | 1.5s | 시계열 분석 윈도우 |
| | `mouth_open_ema_alpha` | 0.35 | EMA 스무딩 계수 |
| **Tracker** | `tracker_out_seconds` | 0.6s | 화면 이탈 판정 최소 시간 |
| | `max_face_speed_screen_per_second` | 2.5 | 최대 얼굴 이동 속도 |
| | `max_match_distance_norm` | 0.25 | 매칭 최대 거리 |
| | `min_area_ratio` / `max_area_ratio` | 0.6 / 1.7 | 면적 게이팅 범위 |
| **Hand** | `no_hand_seconds` | 0.8s | 손 부재 판정 최소 시간 |
| | `desk_y_threshold` | 0.6 | 책상 위 판정 Y 좌표 |
| **Calibration** | `duration_seconds` | 5.0s | 캘리브레이션 시간 |
| | `min_samples` | 20 | 최소 수집 샘플 수 |