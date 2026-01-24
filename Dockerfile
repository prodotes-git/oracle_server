# Python 3.11 슬림 버전을 사용합니다. 가볍고 빠릅니다.
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 포트 설정 (Coolify나 배포 환경에서 이 포트를 봅니다)
EXPOSE 8000

# 서버 실행 명령어
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
