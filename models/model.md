# Models

이 디렉토리에는 Off-Task 감지에 사용되는 YOLO ONNX 모델이 위치합니다.  
모델 파일(`.onnx`)은 용량 문제로 Git에 포함되지 않습니다. 아래 링크에서 다운로드 후 이 디렉토리에 저장하세요.

## 필요 파일

| 파일명 | 설명 |
|--------|------|
| `yolo26n.onnx` | YOLO 기반 핸드폰/물체 감지 모델 |

## 다운로드

**Google Drive**: [다운로드 링크](https://drive.google.com/file/d/1rln_UdyzPi6M2Nzai2ALxNRuIrOr_ndM/view?usp=drive_link)

```bash
# 다운로드 후 이 디렉토리에 저장
mv yolo26n.onnx /path/to/pet/models/
```

## 구성 파일

모델 관련 설정은 `config/off_task.json`에서 관리합니다.  
`model.phone_onnx_path` 항목에서 모델 파일명을 변경할 수 있습니다.
