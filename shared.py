import os
import redis
import pytz
import json
import time
from datetime import datetime

# 시간대 설정
seoul_tz = pytz.timezone('Asia/Seoul')

# 캐시 만료 시간 (1시간)
CACHE_EXPIRE = 3600

# Redis 연결 설정 (환경 변수 지원)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

try:
    r = redis.Redis(
        host=REDIS_HOST, 
        port=6379, 
        password=REDIS_PASSWORD,
        db=0, 
        decode_responses=True,
        socket_timeout=5
    )
    r.ping() # 연결 테스트
    print(f"Connected to Redis at {REDIS_HOST}")
except Exception as e:
    print(f"Warning: Redis connection failed ({e}). Running without cache.")
    r = None

# 서버 시작 시간 기록 (Uptime 계산용)
boot_time = time.time()

def get_cached_data(cache_key, file_path):
    try:
        if r:
            cached = r.get(cache_key)
            if cached:
                cached_json = json.loads(cached)
                return cached_json
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                json_content = json.load(f)
            
            # 파일 내용의 형식 확인 (신규: dict, 기존: list)
            if isinstance(json_content, dict) and 'data' in json_content:
                raw_list = json_content['data']
                last_updated = json_content.get('last_updated')
            else:
                raw_list = json_content
                last_updated = None

            unique_data = []
            seen = set()
            for item in raw_list:
                name = item.get('eventName')
                if name and name not in seen:
                    seen.add(name)
                    unique_data.append(item)
            
            if not last_updated:
                mtime = os.path.getmtime(file_path)
                dt = datetime.fromtimestamp(mtime, tz=pytz.UTC).astimezone(seoul_tz)
                last_updated = dt.strftime('%Y-%m-%d %H:%M:%S')

            res = {'last_updated': last_updated, 'data': unique_data}
            if r: r.setex(cache_key, CACHE_EXPIRE, json.dumps(res))
            return res
    except Exception: pass
    return {'last_updated': None, 'data': []}
