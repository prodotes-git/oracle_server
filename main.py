from fastapi import FastAPI
import os
import redis

app = FastAPI()

# Redis 연결 설정 (Coolify 내부 네트워크 주소 사용)
# 환경 변수가 없으면 기본 'redis' 호스트를 시도합니다.
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/")
def read_root():
    try:
        # Redis를 이용한 간단한 방문자 카운트 (속도가 매우 빠릅니다)
        visits = r.incr("counter")
    except Exception:
        visits = "Redis 연결 안됨"
    
    return {
        "Hello": "World (Faster with Redis)",
        "Visits": visits,
        "Server": "Oracle Cloud Free Tier"
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
