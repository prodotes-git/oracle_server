import httpx
import os
import json
import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import Column, Integer, String, Float, text
from sqlalchemy.orm import Session
from shared import Base, engine, get_db, seoul_tz
from datetime import datetime

router = APIRouter()

# 가맹점 모델 정의
class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String, index=True)  # 'onnuri' or 'gg'
    address = Column(String)
    road_address = Column(String)
    lat = Column(Float, index=True)
    lon = Column(Float, index=True)
    category = Column(String)
    phone = Column(String)
    last_updated = Column(String)

# 테이블 생성 함수
def init_db():
    if engine is not None:
        try:
            Base.metadata.create_all(bind=engine)
            # 기존 테이블에 road_address 컬럼이 없으면 추가
            try:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS road_address VARCHAR"))
                    conn.commit()
            except Exception:
                pass  # 이미 존재하거나 지원하지 않는 DB면 무시
            print("PostgreSQL tables created successfully")
        except Exception as e:
            print(f"Failed to create tables: {e}")

# API Keys
GG_KEY = os.getenv("GG_API_KEY", "54450ac8d7d048f8b26d5cba3b983663")
PUBLIC_DATA_KEY = os.getenv("PUBLIC_DATA_KEY", "af1495f8d5985b1ba537c92f59f43f0454398cd2207b752cbfc11defe011f86f")
KAKAO_REST_KEY = os.getenv("KAKAO_REST_KEY", "83bb425cae47ad6f7f1015aee1993d0f")

@router.get("/local-currency", response_class=HTMLResponse)
def local_currency_page():
    path = os.path.join(os.getcwd(), "templates", "local_currency_map.html")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@router.get("/api/local-currency/merchants")
async def get_merchants(
    lat: float, 
    lon: float, 
    radius: float = Query(default=3.0, ge=0.5, le=20.0),
    type: str = Query(default="onnuri"),
    keyword: str = Query(default=""),
    db: Session = Depends(get_db)
):
    if not db:
        return {"data": [], "message": "Database not connected", "total": 0}
    
    # 위경도 범위 계산 (1도 ≈ 111km, 경도는 위도에 따라 다름)
    lat_delta = radius / 111.0
    lon_delta = radius / (111.0 * abs(cos_deg(lat)))
    
    query = db.query(Merchant).filter(
        Merchant.type == type,
        Merchant.lat.between(lat - lat_delta, lat + lat_delta),
        Merchant.lon.between(lon - lon_delta, lon + lon_delta)
    )
    
    if keyword:
        query = query.filter(
            (Merchant.name.ilike(f"%{keyword}%")) | 
            (Merchant.address.ilike(f"%{keyword}%"))
        )
    
    results = query.limit(200).all()
    
    return {
        "data": [
            {
                "id": m.id,
                "place_name": m.name,
                "address_name": m.address or "",
                "road_address_name": getattr(m, 'road_address', None) or m.address or "",
                "y": m.lat,
                "x": m.lon,
                "phone": m.phone or "",
                "category_name": m.category or ""
            } for m in results
        ],
        "total": len(results)
    }

@router.get("/api/local-currency/stats")
async def get_stats(db: Session = Depends(get_db)):
    if not db:
        return {"onnuri": 0, "gg": 0}
    try:
        onnuri_count = db.query(Merchant).filter(Merchant.type == "onnuri").count()
        gg_count = db.query(Merchant).filter(Merchant.type == "gg").count()
        return {"onnuri": onnuri_count, "gg": gg_count}
    except:
        return {"onnuri": 0, "gg": 0}

import math
def cos_deg(deg):
    return math.cos(math.radians(deg))

@router.post("/api/local-currency/sync")
async def start_sync_tasks(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_all_data)
    return {"status": "sync_started"}

async def sync_all_data():
    print(f"[{datetime.now(seoul_tz)}] Starting full local currency data sync...")
    await sync_gyeonggi_data()
    await sync_onnuri_data()
    print(f"[{datetime.now(seoul_tz)}] Full local currency data sync completed.")

# ─── 경기지역화폐 동기화 ───
async def sync_gyeonggi_data():
    print(f"[{datetime.now(seoul_tz)}] Starting Gyeonggi local currency sync...")
    url = "https://openapi.gg.go.kr/RegionMnyFacltStus"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        db = None
        total_added = 0
        total_skipped = 0
        try:
            from shared import SessionLocal
            if not SessionLocal: return
            db = SessionLocal()
            
            # 기존 경기 데이터 삭제 후 재수집 (깨끗한 데이터 유지)
            deleted = db.query(Merchant).filter(Merchant.type == "gg").delete()
            db.commit()
            print(f"  Cleared {deleted} existing Gyeonggi records.")
            
            # 첫 페이지로 전체 건수 확인
            params = {"KEY": GG_KEY, "Type": "json", "pIndex": 1, "pSize": 1000}
            resp = await client.get(url, params=params)
            data = resp.json()
            
            head = data.get("RegionMnyFacltStus", [{}])[0].get("head", [])
            total_count = 0
            for item in head:
                if "list_total_count" in item:
                    total_count = item["list_total_count"]
                    break
            
            max_pages = min(200, (total_count // 1000) + 1)
            print(f"  Total Gyeonggi merchants: {total_count} ({max_pages} pages)")
            
            for page in range(1, max_pages + 1):
                try:
                    if page > 1:
                        params["pIndex"] = page
                        resp = await client.get(url, params=params)
                        data = resp.json()
                    
                    status_data = data.get("RegionMnyFacltStus", [])
                    if len(status_data) < 2:
                        break
                    
                    items = status_data[1].get("row", [])
                    batch = []
                    for item in items:
                        name = item.get("CMPNM_NM")
                        lat_str = item.get("REFINE_WGS84_LAT")
                        lon_str = item.get("REFINE_WGS84_LOGT")
                        if not name or not lat_str or not lon_str:
                            total_skipped += 1
                            continue
                        
                        try:
                            lat_val = float(lat_str)
                            lon_val = float(lon_str)
                        except (ValueError, TypeError):
                            total_skipped += 1
                            continue
                        
                        # 유효 범위 체크 (한국 위경도)
                        if not (33.0 <= lat_val <= 39.0 and 124.0 <= lon_val <= 132.0):
                            total_skipped += 1
                            continue
                        
                        batch.append(Merchant(
                            name=name,
                            type="gg",
                            address=item.get("REFINE_LOTNO_ADDR") or "",
                            road_address=item.get("REFINE_ROADNM_ADDR") or "",
                            lat=lat_val,
                            lon=lon_val,
                            category=item.get("INDUTYPE_NM") or "",
                            phone=item.get("TELNO") or "",
                            last_updated=datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
                        ))
                    
                    if batch:
                        db.add_all(batch)
                        db.commit()
                        total_added += len(batch)
                    
                    if page % 10 == 0 or page == max_pages:
                        print(f"  Gyeonggi: Page {page}/{max_pages} | Added: {total_added} | Skipped: {total_skipped}")
                        
                except Exception as e:
                    print(f"  Gyeonggi page {page} error: {e}")
                    continue
            
            print(f"[{datetime.now(seoul_tz)}] Gyeonggi sync complete: {total_added} merchants added, {total_skipped} skipped.")
            
        except Exception as e:
            print(f"Gyeonggi sync error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

# ─── 온누리상품권 동기화 ───
async def sync_onnuri_data():
    print(f"[{datetime.now(seoul_tz)}] Starting Onnuri merchant sync...")
    # 공공데이터포털 - 소상공인시장진흥공단_전국 온누리상품권 가맹점 현황
    url = "https://api.odcloud.kr/api/3060079/v1/uddi:7ffa42f8-01d1-4329-aa94-aefb67c53cf1"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        db = None
        total_added = 0
        geocode_fail = 0
        # 시장명별 좌표 캐시 (같은 시장의 가맹점들은 같은 좌표 사용)
        market_coords_cache = {}
        
        try:
            from shared import SessionLocal
            if not SessionLocal: return
            db = SessionLocal()
            
            # 기존 온누리 데이터 삭제 후 재수집
            deleted = db.query(Merchant).filter(Merchant.type == "onnuri").delete()
            db.commit()
            print(f"  Cleared {deleted} existing Onnuri records.")
            
            # 전체 건수 확인 (perPage=1000으로 빠르게 수집)
            params = {"serviceKey": PUBLIC_DATA_KEY, "page": 1, "perPage": 1000}
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                print(f"  Onnuri API error: {resp.status_code} - {resp.text[:200]}")
                return
            
            first_data = resp.json()
            total_count = first_data.get("totalCount", 0)
            max_pages = min(50, (total_count // 1000) + 1)  # 최대 50,000건
            print(f"  Total Onnuri merchants from API: {total_count} ({max_pages} pages)")
            
            for page in range(1, max_pages + 1):
                try:
                    if page > 1:
                        params["page"] = page
                        resp = await client.get(url, params=params)
                        if resp.status_code != 200:
                            print(f"  Onnuri API page {page} error: {resp.status_code}")
                            break
                        page_data = resp.json()
                    else:
                        page_data = first_data
                    
                    items = page_data.get("data", [])
                    if not items:
                        break
                    
                    batch = []
                    for item in items:
                        name = item.get("가맹점명") or item.get("점포명") or item.get("상호")
                        region = item.get("소재지") or ""  # "경기", "광주" 등 시/도만 있음
                        market = item.get("소속 시장명(또는 상점가)") or item.get("시장명") or item.get("시장_상가명") or ""
                        if not name:
                            continue
                        
                        # 시장명+지역으로 좌표를 구함 (캐시 활용)
                        cache_key = f"{market}|{region}"
                        if cache_key in market_coords_cache:
                            lat, lon = market_coords_cache[cache_key]
                        else:
                            lat, lon = None, None
                            # 1차: "시장명 지역" 으로 검색
                            if market:
                                search_query = f"{market} {region}" if region else market
                                lat, lon = await geocode_address(client, search_query)
                            # 2차: "가맹점명 지역" 으로 검색
                            if lat is None and region:
                                lat, lon = await geocode_address(client, f"{name} {region}")
                            
                            market_coords_cache[cache_key] = (lat, lon)
                            # API 부하 방지
                            await asyncio.sleep(0.05)
                        
                        if lat is None or lon is None:
                            geocode_fail += 1
                            continue
                        
                        address_str = f"{region} {market}".strip() if region or market else name
                        batch.append(Merchant(
                            name=name,
                            type="onnuri",
                            address=address_str,
                            road_address=address_str,
                            lat=lat,
                            lon=lon,
                            category=item.get("취급품목") or "",
                            phone="",
                            last_updated=datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
                        ))
                    
                    if batch:
                        db.add_all(batch)
                        db.commit()
                        total_added += len(batch)
                    
                    if page % 5 == 0 or page == max_pages:
                        print(f"  Onnuri: Page {page}/{max_pages} | Added: {total_added} | Geocode fails: {geocode_fail} | Cached markets: {len(market_coords_cache)}")
                    
                except Exception as e:
                    print(f"  Onnuri page {page} error: {e}")
                    continue
            
            print(f"[{datetime.now(seoul_tz)}] Onnuri sync complete: {total_added} merchants added, {geocode_fail} geocode failures, {len(market_coords_cache)} markets cached.")

            
        except Exception as e:
            print(f"Onnuri sync error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

async def geocode_address(client: httpx.AsyncClient, address: str):
    """카카오 REST API를 이용한 지오코딩"""
    if not KAKAO_REST_KEY:
        return None, None
    
    try:
        # 1차: 주소 검색
        resp = await client.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"},
            params={"query": address},
            timeout=10.0
        )
        if resp.status_code == 200:
            docs = resp.json().get("documents", [])
            if docs:
                return float(docs[0]["y"]), float(docs[0]["x"])
        
        # 2차: 키워드 검색 (주소로 못 찾을 때)
        resp = await client.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"},
            params={"query": address, "size": 1},
            timeout=10.0
        )
        if resp.status_code == 200:
            docs = resp.json().get("documents", [])
            if docs:
                return float(docs[0]["y"]), float(docs[0]["x"])
                
    except Exception as e:
        pass  # 개별 실패는 무시
    
    return None, None
