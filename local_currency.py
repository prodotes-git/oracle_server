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
    type = Column(String)  # 'onnuri' or 'gyeonggi'
    address = Column(String)
    lat = Column(Float)
    lon = Column(Float)
    category = Column(String)
    phone = Column(String)
    last_updated = Column(String)

# 테이블 생성
if engine is not None:
    Base.metadata.create_all(bind=engine)

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
    background_tasks.add_task(sync_gyeonggi_data)
    # 온누리 데이터는 양이 방대하므로 별도 처리 필요
    return {"status": "sync_started"}

async def sync_gyeonggi_data():
    print("Starting Gyeonggi Local Currency sync...")
    url = "https://openapi.gg.go.kr/RegionMnyFacltStus"
    params = {
        "KEY": GG_KEY,
        "Type": "json",
        "pIndex": 1,
        "pSize": 1000
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            db = next(get_db())
            if not db: return
            
            # 한 번에 1000개씩 가져와서 저장 (샘플로 5페이지 정도만 먼저 구현)
            for i in range(1, 10):
                params["pIndex"] = i
                resp = await client.get(url, params=params)
                data = resp.json()
                
                rows = data.get("RegionMnyFacltStus", [])
                if len(rows) < 2: break
                
                items = rows[1].get("row", [])
                for item in items:
                    name = item.get("CMPNM_NM")
                    lat = item.get("REFINE_WGS84_LAT")
                    lon = item.get("REFINE_WGS84_LOGT")
                    
                    if not lat or not lon: continue
                    
                    # 중복 확인 및 저장
                    existing = db.query(Merchant).filter(Merchant.name == name, Merchant.lat == float(lat)).first()
                    if not existing:
                        merchant = Merchant(
                            name=name,
                            type="gyeonggi",
                            address=item.get("REFINE_ROADNM_ADDR") or item.get("REFINE_LOTNO_ADDR"),
                            lat=float(lat),
                            lon=float(lon),
                            category=item.get("INDUTYPE_NM"),
                            phone=item.get("TELNO"),
                            last_updated=datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
                        )
                        db.add(merchant)
                db.commit()
                print(f"Gyeonggi sync: Page {i} completed")
        except Exception as e:
            print(f"Gyeonggi sync error: {e}")

# TODO: 온누리 데이터 싱크 로직 추가 (API 스펙에 맞춰 구현 필요)
