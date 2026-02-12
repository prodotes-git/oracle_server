import os
import redis
import json

# Redis connection settings
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_USERNAME = os.getenv("REDIS_USERNAME", "default")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "2AplNlOnk1oW2FnH6mwVlO5i3MTXOIjyzF5HDoIQAF7k180NekGzpieGEE0yEOdW")

def test_redis():
    print(f"Connecting to Redis at {REDIS_HOST} with username '{REDIS_USERNAME}'...")
    try:
        r = redis.Redis(
            host=REDIS_HOST, 
            port=6379, 
            username=REDIS_USERNAME,
            password=REDIS_PASSWORD,
            db=0, 
            decode_responses=True,
            socket_timeout=5
        )
        r.ping()
        print("✅ Redis connection successful!")
        
        # Test basic operations
        r.set("test_key", "hello")
        val = r.get("test_key")
        print(f"Test get key: {val}")
        r.delete("test_key")
        
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")

if __name__ == "__main__":
    test_redis()
