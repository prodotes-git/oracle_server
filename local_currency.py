import httpx
import os
import json
from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy import Column, Integer, String, Float, Index
from sqlalchemy.orm import Session
from shared import Base, engine, get_db, seoul_tz
from datetime import datetime

router = APIRouter()

# 가맹점 모델 정의
class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String)  # 'onnuri' or 'gg'
    address = Column(String)
    lat = Column(Float)
    lon = Column(Float)
    category = Column(String)
    phone = Column(String)
    last_updated = Column(String)

# 테이블 생성 함수
def init_db():
    if engine is not None:
        try:
            Base.metadata.create_all(bind=engine)
            print("PostgreSQL tables created successfully")
        except Exception as e:
            print(f"Failed to create tables: {e}")

# API Keys
GG_KEY = "54450ac8d7d048f8b26d5cba3b983663"
PUBLIC_DATA_KEY = "af1495f8d5985b1ba537c92f59f43f0454398cd2207b752cbfc11defe011f86f"

@router.get("/local-currency", response_class=HTMLResponse)
def local_currency_page():
    path = os.path.join("templates", "local_currency_map.html")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@router.get("/api/local-currency/merchants")
async def get_merchants(lat: float, lon: float, radius: float = 2.0, type: str = "onnuri", db: Session = Depends(get_db)):
    if not db:
        return {"data": [], "message": "Database not connected"}
    
    # 단순 위경도 사각형 범위로 필터링 (성능을 위해)
    # 0.01 degree ~= 1.1km
    delta = radius * 0.01
    
    results = db.query(Merchant).filter(
        Merchant.type == type,
        Merchant.lat.between(lat - delta, lat + delta),
        Merchant.lon.between(lon - delta, lon + delta)
    ).limit(500).all()
    
    return {"data": [
        {
            "id": m.id,
            "place_name": m.name,
            "address_name": m.address,
            "y": m.lat,
            "x": m.lon,
            "phone": m.phone,
            "category_name": m.category
        } for m in results
    ]}

@router.post("/api/local-currency/sync")
async def start_sync_tasks(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_all_data)
    return {"status": "sync_started"}

async def sync_all_data():
    await sync_gyeonggi_data()
    await sync_onnuri_data()

async def sync_gyeonggi_data():
    print("Starting Gyeonggi Local Currency sync...")
    url = "https://openapi.gg.go.kr/RegionMnyFacltStus"
    params = {
        "KEY": GG_KEY,
        "Type": "json",
        "pIndex": 1,
        "pSize": 1000
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        db = None
        try:
            from shared import SessionLocal
            db = SessionLocal()
            if not db: return

            # 첫 페이지를 가져와서 전체 개수 확인
            resp = await client.get(url, params=params)
            data = resp.json()
            
            head = data.get("RegionMnyFacltStus", [{}])[0].get("head", [])
            total_count = 0
            for item in head:
                if "list_total_count" in item:
                    total_count = item["list_total_count"]
                    break
            
            print(f"Total Gyeonggi merchants found: {total_count}")
            # 너무 많으므로 일단 최대 10만건까지만 수집 (100페이지)
            max_pages = min(100, (total_count // 1000) + 1)
            
            for i in range(1, max_pages + 1):
                params["pIndex"] = i
                if i > 1: # 첫 페이지는 이미 가져왔으므로
                    resp = await client.get(url, params=params)
                    data = resp.json()
                
                status_data = data.get("RegionMnyFacltStus", [])
                if len(status_data) < 2: break
                
                items = status_data[1].get("row", [])
                new_count = 0
                for item in items:
                    name = item.get("CMPNM_NM")
                    lat = item.get("REFINE_WGS84_LAT")
                    lon = item.get("REFINE_WGS84_LOGT")
                    if not lat or not lon: continue
                    
                    # 중복 확인 (이름과 좌표 기준) - 성능을 위해 한번에 처리하는 것이 좋으나 우선 유지
                    existing = db.query(Merchant).filter(
                        Merchant.name == name,
                        Merchant.lat == float(lat),
                        Merchant.lon == float(lon)
                    ).first()
                    
                    if not existing:
                        merchant = Merchant(
                            name=name,
                            type="gg",
                            address=item.get("REFINE_ROADNM_ADDR") or item.get("REFINE_LOTNO_ADDR"),
                            lat=float(lat),
                            lon=float(lon),
                            category=item.get("INDUTYPE_NM"),
                            phone=item.get("TELNO"),
                            last_updated=datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
                        )
                        db.add(merchant)
                        new_count += 1
                
                db.commit()
                print(f"Gyeonggi sync: Page {i}/{max_pages} completed. Added {new_count} new records.")
                
        except Exception as e:
            print(f"Gyeonggi sync error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

# Kakao REST API Key (for geocoding)
KAKAO_REST_KEY = os.getenv("KAKAO_REST_KEY", "8220fce5d491da93dda89d8cf3682514") # JS Key may sometimes work or User should provide REST Key

async def get_coordinates(address):
    if not KAKAO_REST_KEY:
        return None, None
    
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    params = {"query": address}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                documents = data.get("documents", [])
                if documents:
                    return float(documents[0]["y"]), float(documents[0]["x"])
    except Exception as e:
        print(f"Geocoding error for {address}: {e}")
    return None, None

async def sync_onnuri_data():
    print("Starting Onnuri Merchant sync (New API)...")
    # 신규 API 엔드포인트
    url = "https://api.odcloud.kr/api/3060079/v1/uddi:7ffa42f8-01d1-4329-aa94-aefb67c53cf1"
    params = {
        "serviceKey": PUBLIC_DATA_KEY,
        "page": 1,
        "perPage": 100
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        db = None
        try:
            from shared import SessionLocal
            db = SessionLocal()
            if not db: return
            
            # 최대 20페이지(2000건) 수집 시도 (지오코딩 할당량 고려)
            for i in range(1, 21):
                params["page"] = i
                resp = await client.get(url, params=params)
                if resp.status_code != 200: 
                    print(f"Onnuri API error: {resp.status_code}")
                    break
                
                data = resp.json()
                items = data.get("data", [])
                if not items: break
                
                new_count = 0
                for item in items:
                    name = item.get("가맹점명")
                    address = item.get("소재지")
                    if not name or not address: continue
                    
                    # 중복 확인
                    existing = db.query(Merchant).filter(
                        Merchant.name == name,
                        Merchant.address == address
                    ).first()
                    
                    if not existing:
                        # 좌표가 없으므로 지오코딩 수행
                        lat, lon = await get_coordinates(address)
                        if not lat or not lon: continue
                        
                        merchant = Merchant(
                            name=name,
                            type="onnuri",
                            address=address,
                            lat=lat,
                            lon=lon,
                            category=item.get("취급품목") or "전통시장",
                            phone=None, # 이 API에는 전화번호 없음
                            last_updated=datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
                        )
                        db.add(merchant)
                        new_count += 1
                
                db.commit()
                print(f"Onnuri sync: Page {i} completed. Added {new_count} new records.")
                
        except Exception as e:
            print(f"Onnuri sync error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()
