# Models

이 디렉토리에는 Off-Task 감지에 사용되는 YOLO ONNX 모델이 위치합니다.  
모델 파일(`.onnx`)은 용량 문제로 Git에 포함되지 않습니다. 아래 링크에서 다운로드 후 이 디렉토리에 저장하세요.

## 필요 파일

| 파일명 | 설명 |
|--------|------|
| `yolo26n.onnx` | COCO 사전학습 YOLO 기반 핸드폰/물체 감지 모델 (기본) |
| `best_fine_tune_freeze.onnx` | 공부 환경 특화 파인튜닝 모델 (**권장**) |

## 다운로드

| 모델 | Google Drive |
|------|-------------|
| `yolo26n.onnx` (기본) | [다운로드](https://drive.google.com/file/d/1rln_UdyzPi6M2Nzai2ALxNRuIrOr_ndM/view?usp=drive_link) |
| `best_fine_tune_freeze.onnx` (파인튜닝) | [다운로드](https://drive.google.com/file/d/1m35mXNHtY9qq1AL50VQU1-VcLC6GYoiy/view?usp=drive_link) |

```bash
# 다운로드 후 이 디렉토리에 저장
mv best_fine_tune_freeze.onnx /path/to/study-with-pet/models/
```

## 모델 비교

### 기본 모델 (`yolo26n.onnx`)

- **Base**: YOLOv11 Nano (COCO 80 클래스 사전학습)
- **탐지 클래스**: 28개 (cell phone, remote, scissors 등)
- **특징**: 범용 COCO 가중치 그대로 사용

### 파인튜닝 모델 (`best_fine_tune_freeze.onnx`) — 권장

- **Base**: YOLOv11 Nano → 공부 환경 특화 Fine-Tuning (Backbone Freeze)
- **탐지 클래스**: 4개 (공부 방해에 직접적인 객체만 선별)
- **PTQ INT8 양자화** 적용으로 경량화

| Class ID | 클래스명 |
|----------|----------|
| 0 | bottle |
| 1 | cup |
| 2 | cell phone |
| 3 | toothbrush |

## 구성 파일

모델 관련 설정은 `config/off_task.json`에서 관리합니다.

### 파인튜닝 모델 사용 시 설정 변경

`config/off_task.json`의 `model` 섹션을 아래와 같이 수정하세요:

```json
{
  "model": {
    "phone_onnx_path": "best_fine_tune_freeze.onnx",
    "phone_labels": {
      "0": "bottle",
      "1": "cup",
      "2": "cell phone",
      "3": "toothbrush"
    }
  }
}
```

### 기본 모델 사용 시 (기존 설정 유지)

```json
{
  "model": {
    "phone_onnx_path": "yolo26n.onnx",
    "phone_labels": {
      "67": "cell phone",
      "65": "remote",
      ...
    }
  }
}
```
