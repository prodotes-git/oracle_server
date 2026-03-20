import os
import redis
import pytz
import json
import time
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 시간대 설정
seoul_tz = pytz.timezone('Asia/Seoul')

# 캐시 만료 시간 (1시간)
CACHE_EXPIRE = 3600

# Redis 연결 설정 (환경 변수 지원)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_USERNAME = os.getenv("REDIS_USERNAME", "default")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "2AplNlOnk1oW2FnH6mwVlO5i3MTXOIjyzF5HDoIQAF7k180NekGzpieGEE0yEOdW")

class LazyRedis:
    """Redis 지연 연결 래퍼.
    import 시점이 아닌 첫 사용 시점에 연결합니다.
    Coolify 배포 시 앱 컨테이너가 Redis보다 먼저 시작되어도
    Uvicorn이 즉시 listen 상태가 될 수 있도록 합니다.
    
    기존 코드의 `if r:` → `r.get()`/`r.setex()` 패턴과 100% 호환됩니다.
    """

    def __init__(self):
        self._client = None
        self._initialized = False

    def _connect(self):
        if self._initialized:
            return
        self._initialized = True
        try:
            redis_args = {
                "host": REDIS_HOST,
                "port": 6379,
                "password": REDIS_PASSWORD,
                "db": 0,
                "decode_responses": True,
                "socket_timeout": 5
            }
            if REDIS_USERNAME and REDIS_USERNAME != "default":
                redis_args["username"] = REDIS_USERNAME

            self._client = redis.Redis(**redis_args)
            self._client.ping()
            print(f"Connected to Redis at {REDIS_HOST}")
        except Exception as e:
            print(f"Warning: Redis connection failed ({e}). Running without cache.")
            self._client = None

    def __bool__(self):
        self._connect()
        return self._client is not None

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        self._connect()
        if self._client:
            return getattr(self._client, name)
        # 연결 실패 시 안전한 no-op 반환
        return lambda *args, **kwargs: None

r = LazyRedis()

# PostgreSQL 설정
DATABASE_URL = os.getenv("DATABASE_URL")
engine = None
SessionLocal = None
Base = declarative_base()

if DATABASE_URL:
    try:
        # Coolify/Docker 환경에서 호환성을 위해 조절
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        engine = create_engine(
            DATABASE_URL, 
            pool_pre_ping=True,
            connect_args={'connect_timeout': 5}
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        print("Connected to PostgreSQL")
    except Exception as e:
        print(f"PostgreSQL connection failed: {e}")

def get_db():
    if SessionLocal:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    else:
        yield None

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
