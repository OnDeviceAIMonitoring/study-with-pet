#!/bin/bash
# Study With Pet 런처
# 바탕화면에서 더블 클릭하여 실행

PROJECT_DIR="/home/willtek/work/pet"
VENV="$PROJECT_DIR/.venv/bin/activate"
SERVER="http://10.56.130.242:8000"
ROOM="TEST_ROOM"

# 가상환경 활성화
source "$VENV"

# 화상 키보드로 이름 입력 받기
NAME=$(python "$PROJECT_DIR/launch/name_input.py")
if [[ $? -ne 0 || -z "$NAME" ]]; then
    echo "이름 입력이 취소되었습니다."
    exit 1
fi

# 클라이언트 실행
cd "$PROJECT_DIR"
exec python frontend/main.py \
    --server "$SERVER" \
    --room "$ROOM" \
    --name "$NAME"
