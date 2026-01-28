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
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        db = None
        try:
            from shared import SessionLocal
            db = SessionLocal()
            
            for i in range(1, 11): # 10,000건 수집
                params["pIndex"] = i
                resp = await client.get(url, params=params)
                data = resp.json()
                
                status_data = data.get("RegionMnyFacltStus", [])
                if len(status_data) < 2: break
                
                items = status_data[1].get("row", [])
                for item in items:
                    name = item.get("CMPNM_NM")
                    lat = item.get("REFINE_WGS84_LAT")
                    lon = item.get("REFINE_WGS84_LOGT")
                    if not lat or not lon: continue
                    
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
                db.commit()
                print(f"Gyeonggi sync: Page {i} completed")
        except Exception as e:
            print(f"Gyeonggi sync error: {e}")
        finally:
            if db: db.close()

async def sync_onnuri_data():
    print("Starting Onnuri Merchant sync...")
    url = "http://api.data.go.kr/opensource/onnuri/merchants"
    params = {
        "serviceKey": PUBLIC_DATA_KEY,
        "type": "json",
        "numOfRows": 1000,
        "pageNo": 1
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        db = None
        try:
            from shared import SessionLocal
            db = SessionLocal()
            
            for i in range(1, 6): # 5,000건 우선 수집
                params["pageNo"] = i
                resp = await client.get(url, params=params)
                if resp.status_code != 200: break
                
                data = resp.json()
                items = data.get("response", {}).get("body", {}).get("items", [])
                if not items: break
                
                for item in items:
                    name = item.get("mktNm") 
                    lat = item.get("lat")
                    lon = item.get("lng")
                    if not lat or not lon: continue
                    
                    existing = db.query(Merchant).filter(
                        Merchant.name == name,
                        Merchant.lat == float(lat)
                    ).first()
                    
                    if not existing:
                        merchant = Merchant(
                            name=name,
                            type="onnuri",
                            address=item.get("rdnmadr") or item.get("lnmadr"),
                            lat=float(lat),
                            lon=float(lon),
                            category="전통시장",
                            phone=item.get("phoneNumber"),
                            last_updated=datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
                        )
                        db.add(merchant)
                db.commit()
                print(f"Onnuri sync: Page {i} completed")
        except Exception as e:
            print(f"Onnuri sync error: {e}")
        finally:
            if db: db.close()
