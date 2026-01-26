import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
import os
import redis
import psutil
import time
import json
import ssl
import pytz
from datetime import datetime

app = FastAPI()

# Redis 연결 시도 (실패 시 r=None으로 처리하여 앱이 죽지 않게 함)
try:
    r = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
    r.ping() # 연결 테스트
except Exception as e:
    print(f"Warning: Redis connection failed ({e}). Running without cache.")
    r = None

# 서버 시작 시간 기록 (Uptime 계산용)
boot_time = time.time()

# 데이터 캐싱을 위한 설정
SHINHAN_CACHE_KEY = "shinhan_card_events_cache_v1"
SHINHAN_MYSHOP_CACHE_KEY = "shinhan_myshop_cache_v3"
KB_CACHE_KEY = "kb_card_events_cache_v1"
HANA_CACHE_KEY = "hana_card_events_cache_v1"
WOORI_CACHE_KEY = "woori_card_events_cache_v1"
BC_CACHE_KEY = "bc_card_events_cache_v1"
SAMSUNG_CACHE_KEY = "samsung_card_events_cache_v1"
HYUNDAI_CACHE_KEY = "hyundai_card_events_cache_v1"
LOTTE_CACHE_KEY = "lotte_card_events_cache_v1"
KFCC_CACHE_KEY = "kfcc_rates_cache_v1"
CACHE_EXPIRE = 3600  # 1시간 동안 캐시 유지
seoul_tz = pytz.timezone('Asia/Seoul')

def get_cached_data(cache_key, file_path):
    try:
        if r:
            cached = r.get(cache_key)
            if cached:
                cached_json = json.loads(cached)
                # Redis에 저장된 데이터의 시간대 보정 (필요한 경우)
                return cached_json
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                json_content = json.load(f)
            
            # 파일 내용의 형식 확인 (신규: dict, 기존: list)
            if isinstance(json_content, dict) and 'data' in json_content:
                raw_list = json_content['data']
                # 파일 내부에 last_updated가 있으면 우선 사용
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
            
            # 파일 내부 시간이 없으면 파일 수정 시간(mtime) 사용
            if not last_updated:
                mtime = os.path.getmtime(file_path)
                dt = datetime.fromtimestamp(mtime, tz=pytz.UTC).astimezone(seoul_tz)
                last_updated = dt.strftime('%Y-%m-%d %H:%M:%S')

            res = {'last_updated': last_updated, 'data': unique_data}
            if r: r.setex(cache_key, CACHE_EXPIRE, json.dumps(res))
            return res
    except Exception: pass
    return {'last_updated': None, 'data': []}


@app.get("/api/shinhan-myshop")
async def get_shinhan_myshop():
    """
    신한카드 마이샵 쿠폰 데이터를 가져와서 정제하여 반환합니다.
    """
    try:
        import json
        cached = r.get(SHINHAN_MYSHOP_CACHE_KEY)
        if cached:
            return json.loads(cached)

        api_url = "https://www.shinhancard.com/mob/MOBFM501N/MOBFM501R21.ajax"
        base_url = "https://www.shinhancard.com"
        
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc",

            "Origin": base_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        }
        payload = {"QY_CCD": "T"}
        
        all_coupons = []
        seen_names = set()
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # 1. 먼저 메인 페이지를 방문하여 기본 쿠키를 확보합니다.
            await client.get(f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc", headers={"User-Agent": headers["User-Agent"]})
            
            # 2. AJAX 요청을 보냅니다.
            response = await client.post(api_url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                msg = data.get("mbw_message")
                
                # mbw_message가 딕셔너리인 경우에만 GRID1을 처리합니다.
                if isinstance(msg, dict):
                    grid = msg.get("GRID1", {})
                    names = grid.get("SSG_NM", [])
                    benefits = grid.get("MCT_CRD_SV_RG_TT", [])
                    imgs = grid.get("MYH_CUP_IMG_URL_AR", [])
                    ends = grid.get("MCT_PLF_MO_EDD", [])
                    links = grid.get("MYH_SRM_ONL_SPP_MLL_URL_AR", [])
                    
                    for i in range(len(names)):
                        name = names[i]
                        benefit = benefits[i] if i < len(benefits) else ""
                        full_name = f"[{name}] {benefit}".strip()
                        if full_name in seen_names: continue
                        seen_names.add(full_name)

                        img = imgs[i] if i < len(imgs) else ""
                        end = ends[i] if i < len(ends) else ""
                        link = links[i] if i < len(links) else f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc"
                        
                        if img and not img.startswith('http'):
                            img = f"{base_url}{img}"
                        if link and not link.startswith('http'):
                            link = f"{base_url}{link}"

                        if len(end) == 8:
                            end = f"~ {end[:4]}.{end[4:6]}.{end[6:]}"

                        all_coupons.append({
                            "category": "마이샵 쿠폰",
                            "eventName": full_name,
                            "period": end,
                            "link": link,
                            "image": img,
                            "bgColor": "#ffffff"
                        })
                else:
                    print(f"Shinhan MyShop API returned message: {msg}")

        return {"data": all_coupons}
    except Exception as e:
        print(f"Shinhan MyShop API Error: {e}")
        return {"data": []}

# 신한카드 데이터 갱신 (백그라운드)
async def crawl_shinhan_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Shinhan background crawl...")
        all_events = []
        seen_titles = set()
        base_url = "https://www.shinhancard.com"
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            # 신한카드는 01, 02... 형식의 JSON 파일을 사용
            for i in range(1, 10): # 페이지 범위 확대
                api_url = f"{base_url}/logic/json/evnPgsList0{i}.json"
                headers = {
                    "Referer": "https://www.shinhancard.com/",
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
                }
                
                try:
                    response = await client.get(api_url, headers=headers)
                    if response.status_code != 200:
                        continue
                    
                    data = response.json()
                    events = data.get("root", {}).get("evnlist", [])
                    if not events:
                        continue
                    
                    for ev in events:
                        title = ev.get('mobWbEvtNm', '')
                        sub_title = ev.get('evtImgSlTilNm', '')
                        if sub_title and sub_title != title:
                            title = f"{title} ({sub_title})" if sub_title else title
                        
                        clean_title = title.strip()
                        if clean_title in seen_titles: continue
                        seen_titles.add(clean_title)

                        start = ev.get('mobWbEvtStd', '')
                        end = ev.get('mobWbEvtEdd', '')
                        if len(start) == 8: start = f"{start[:4]}.{start[4:6]}.{start[6:]}"
                        if len(end) == 8: end = f"{end[:4]}.{end[4:6]}.{end[6:]}"
                        
                        img_url = ev.get('hpgEvtCtgImgUrlAr', '')
                        if img_url and not img_url.startswith('http'):
                            img_url = f"{base_url}{img_url}"
                        
                        link_url = ev.get('hpgEvtDlPgeUrlAr', '')
                        if link_url and not link_url.startswith('http'):
                            link_url = f"{base_url}{link_url}"
                            
                        all_events.append({
                            "category": ev.get('hpgEvtKindNm', '이벤트'),
                            "eventName": clean_title,
                            "period": f"{start} ~ {end}",
                            "link": link_url,
                            "image": img_url,
                            "bgColor": "#ffffff"
                        })
                except Exception: continue

        if all_events:
            try:
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("shinhan_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                
                if r:
                    try:
                        r.setex(SHINHAN_CACHE_KEY, CACHE_EXPIRE, json.dumps(output_data))
                    except Exception as re:
                        print(f"Shinhan Redis save failed: {re}")
                print(f"[{datetime.now(seoul_tz)}] Shinhan crawl finished. {len(all_events)} events.")
            except Exception as fe:
                print(f"Shinhan file save failed: {fe}")
            
    except Exception as e:
        print(f"[{datetime.now(seoul_tz)}] Shinhan crawl failed: {e}")

# KB카드 데이터 갱신 (백그라운드)
# KB카드 데이터 갱신 (백그라운드)
async def crawl_kb_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting KB background crawl...")
        all_events = []
        seen_ids = set()
        api_url = "https://m.kbcard.com/BON/API/MBBACXHIABNC0064"
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            for page in range(1, 50): 
                payload = {
                    "evntStatus": "", "evntBonTag": "", "evntScp": "", 
                    "evntAi": "", "evntVip": "", "pageCount": page, "evtName": ""
                }
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://m.kbcard.com/BON/DVIEW/MBBMCXHIABNC0022",
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
                }
                try:
                    response = await client.post(api_url, data=payload, headers=headers)
                    if response.status_code != 200: break
                    res_json = response.json()
                    events = res_json.get("evntList", [])
                    if not events: break
                    
                    for ev in events:
                        evt_no = ev.get('evtNo', '')
                        # 중복 제거 핵심 로직
                        if not evt_no or evt_no in seen_ids: continue
                        seen_ids.add(evt_no)
                        
                        category_code = ev.get("evntBonContents", "")
                        category_map = {"01": "포인트/캐시백", "02": "할인/무이자", "03": "경품", "04": "기타"}
                        category = category_map.get(category_code, "이벤트")
                        
                        img_path = ev.get('evtImgPath', '')
                        if img_path and not img_path.startswith('http'):
                            img_path = f"https://img1.kbcard.com/ST/img/cxc{img_path}"

                        link = f"https://m.kbcard.com/BON/DVIEW/MBBMCXHIABNC0026?evntSerno={evt_no}&evntMain=Y"

                        all_events.append({
                            "category": category,
                            "eventName": f"{ev.get('evtNm', '')} {ev.get('evtSubNm', '')}".strip(),
                            "period": ev.get("evtYMD", ""),
                            "link": link,
                            "image": img_path,
                            "bgColor": "#ffffff"
                        })
                    
                    if page >= int(res_json.get("totalPageCount", 0)): break
                except Exception as e:
                    print(f"Error parsing KB page {page}: {e}")
                    break
        
        if all_events:
            try:
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("kb_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                if r: r.setex(KB_CACHE_KEY, CACHE_EXPIRE, json.dumps(output_data))
                print(f"[{datetime.now(seoul_tz)}] KB crawl finished. {len(all_events)} events.")
            except Exception as e: print(e)
            
    except Exception as e:
        print(f"[{datetime.now(seoul_tz)}] KB crawl failed: {e}")

@app.get("/api/shinhan-cards")
async def get_shinhan_cards():
    return get_cached_data(SHINHAN_CACHE_KEY, 'shinhan_data.json')

@app.get("/api/kb-cards")
async def get_kb_cards():
    return get_cached_data(KB_CACHE_KEY, 'kb_data.json')

@app.post("/api/shinhan/update")
async def update_shinhan(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_shinhan_bg)
    return {"status": "started"}

@app.post("/api/kb/update")
async def update_kb(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_kb_bg)
    return {"status": "started"}

HANA_CACHE_KEY = "hana_card_events_cache_v1"

# 하나카드 데이터 갱신 (백그라운드)
async def crawl_hana_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Hana background crawl...")
        all_events = []
        base_url = "https://m.hanacard.co.kr"
        api_url = "https://m.hanacard.co.kr/MKEVT1000M.ajax"

        # SSL Context 설정 (DH_KEY_TOO_SMALL 해결)
        import ssl
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            # OpenSSL 3.0 이상에서 DH Key 허용을 위해 보안 레벨 낮춤
            ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        except Exception:
            ssl_context = False

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=ssl_context) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://m.hanacard.co.kr",
                "Referer": "https://m.hanacard.co.kr/MKEVT1000M.web"
            }
            
            for page in range(1, 40): # 충분한 페이지 수
                data = {
                    "evnCate": "00000",
                    "page": str(page),
                    "schTxt": "",
                    "schVipYn": "N",
                    "orderType": "N",
                    "srchF": "A",
                    "srchV": "",
                    "ctgId": "0" 
                }
                
                try:
                    response = await client.post(api_url, data=data, headers=headers)
                    if response.status_code != 200:
                        break
                    
                    # 하나카드 API는 EUC-KR 인코딩 사용
                    try:
                        res_text = response.content.decode("euc-kr")
                    except UnicodeDecodeError:
                        res_text = response.text
                        
                    res_json = json.loads(res_text)
                    
                    # 응답 구조: DATA -> eventListMap -> list
                    data_obj = res_json.get("DATA", {})
                    event_map = data_obj.get("eventListMap", {})
                    event_list = event_map.get("list", [])
                    
                    if not event_list:
                        break
                        
                    seen_titles = set()
                    for ev in event_list:
                        # 필드 매핑
                        title = ev.get("EVN_TIT_NM", "").strip()
                        if not title or title in seen_titles: continue
                        seen_titles.add(title)

                        category = ev.get("ITG_APP_EVN_MC_NM", "이벤트")
                        start_date = ev.get("EVN_SDT", "")
                        end_date = ev.get("EVN_EDT", "")
                        seq = ev.get("EVN_SEQ", "")
                        
                        img_path = ev.get("APN_FILE_NM", "")
                        if img_path and not img_path.startswith("http"):
                            img_path = f"{base_url}{img_path}"
                            
                        link = ""
                        if seq:
                            link = f"{base_url}/MKEVT1010M.web?EVN_SEQ={seq}"
                        
                        all_events.append({
                            "category": category,
                            "eventName": title,
                            "period": f"{start_date} ~ {end_date}",
                            "link": link,
                            "image": img_path,
                            "bgColor": "#ffffff"
                        })

                    # 페이지 종료 체크
                    total_page = int(event_map.get("totalPage", 0))
                    if page >= total_page:
                        break
                        
                except Exception as e:
                    print(f"Error parsing Hana page {page}: {e}")
                    # API 호출 실패 시 중단하지 않고 다음 시도 (혹은 중단)
                    # 여기서는 안전하게 중단
                    break

        if all_events:
            try:
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("hana_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                if r:
                    try:
                        r.setex(HANA_CACHE_KEY, CACHE_EXPIRE, json.dumps(output_data))
                    except Exception as re:
                         print(f"Hana Redis save failed: {re}")
                print(f"[{datetime.now(seoul_tz)}] Hana crawl finished. {len(all_events)} events.")
            except Exception as fe:
                print(f"Hana save failed: {fe}")
            
    except Exception as e:
        print(f"[{datetime.now(seoul_tz)}] Hana crawl failed: {e}")

@app.get("/api/hana-cards")
async def get_hana_cards():
    return get_cached_data(HANA_CACHE_KEY, 'hana_data.json')

@app.post("/api/hana/update")
async def update_hana(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_hana_bg)
    return {"status": "started"}

def get_uptime():
    uptime_seconds = int(time.time() - boot_time)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m"

@app.get("/api/kfcc")
async def get_kfcc_data():
    """
    새마을금고 금리 데이터를 반환합니다.
    1. Redis 캐시 우선 확인
    2. 캐시 없으면 로컬 파일 확인
    3. 둘 다 없으면 빈 데이터 반환
    """
    try:
        import json
        # Redis 캐시 확인 (Redis 연결이 있을 때만)
        if r:
            try:
                cached_data = r.get(KFCC_CACHE_KEY)
                if cached_data:
                    return json.loads(cached_data)
            except Exception as redis_error:
                print(f"Redis error: {redis_error}")
            
        # 로컬 파일 확인
        local_path = "kfcc_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # 파일 수정 시간 가져오기
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            response_data = {
                "last_updated": last_updated,
                "data": data
            }
            
            # Redis에 캐시 저장 시도
            if r:
                try:
                    r.setex(KFCC_CACHE_KEY, CACHE_EXPIRE, json.dumps(response_data))
                except Exception:
                    pass
            return response_data

        # 로컬 파일도 없으면 빈 값 반환
        return {"last_updated": None, "message": "데이터가 없습니다.", "data": []}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")

@app.get("/kfcc", response_class=HTMLResponse)
def view_kfcc_page():
    try:
        with open("kfcc.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "kfcc.html not found"

@app.post("/api/kfcc/update")
async def update_kfcc_data(background_tasks: BackgroundTasks):
    """
    새마을금고 데이터 크롤링을 백그라운드에서 실행합니다.
    """
    background_tasks.add_task(background_crawl_kfcc)
    return {"status": "started", "message": "KFCC data update started in background."}

async def background_crawl_kfcc():
    try:
        print(f"[{datetime.now(seoul_tz)}] ========== Starting KFCC background crawl ==========")
        from kfcc_crawler import run_crawler
        # json은 상단 import 사용
        
        data = await run_crawler()
        
        print(f"[{datetime.now(seoul_tz)}] Crawler returned {len(data)} records")
        
        if not data:
            print(f"[{datetime.now(seoul_tz)}] WARNING: No data collected from crawler!")
            return
        
        # 파일 및 캐시 저장 데이터 구성
        current_time = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
        save_data = {
            "last_updated": current_time,
            "data": data
        }
        
        # 파일 저장
        try:
            with open("kfcc_data.json", "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            print(f"[{datetime.now(seoul_tz)}] Successfully saved to kfcc_data.json")
        except Exception as fe:
            print(f"[{datetime.now(seoul_tz)}] ERROR: KFCC file save failed: {fe}")
            import traceback
            traceback.print_exc()
            
        # 캐시 갱신
        if r:
            try:
                r.setex(KFCC_CACHE_KEY, CACHE_EXPIRE, json.dumps(save_data, ensure_ascii=False))
                print(f"[{datetime.now(seoul_tz)}] Successfully updated Redis cache")
            except Exception as re:
                print(f"[{datetime.now(seoul_tz)}] ERROR: KFCC Redis save failed: {re}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[{datetime.now(seoul_tz)}] WARNING: Redis not available, skipped cache update.")
                
        print(f"[{datetime.now(seoul_tz)}] ========== KFCC background crawl finished. {len(data)} records updated ==========")
    except Exception as e:
        print(f"[{datetime.now(seoul_tz)}] ========== KFCC background crawl FAILED ==========")
        print(f"[{datetime.now(seoul_tz)}] ERROR: {e}")
        import traceback
        traceback.print_exc()

# 스케줄러 설정
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

scheduler = AsyncIOScheduler(timezone=seoul_tz)

@app.on_event("startup")
async def start_scheduler():
    # 매일 새벽 4시에 KFCC 크롤링 실행
    scheduler.add_job(background_crawl_kfcc, 'cron', hour=4, minute=0)
    # 4시 5분에 신한카드
    scheduler.add_job(crawl_shinhan_bg, 'cron', hour=4, minute=5)
    # 4시 10분에 KB카드
    scheduler.add_job(crawl_kb_bg, 'cron', hour=4, minute=10)
    # 4시 15분에 하나카드
    scheduler.add_job(crawl_hana_bg, 'cron', hour=4, minute=15)
    # 4시 20분에 우리카드
    scheduler.add_job(crawl_woori_bg, 'cron', hour=4, minute=20)
    # 4시 25분에 BC카드
    scheduler.add_job(crawl_bc_bg, 'cron', hour=4, minute=25)
    # 4시 30분에 삼성카드
    scheduler.add_job(crawl_samsung_bg, 'cron', hour=4, minute=30)
    
    scheduler.start()
    print("Scheduler started. All tasks scheduled.")

@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        visits = r.incr("counter")
    except Exception:
        visits = "---"
    
    cpu_usage = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    uptime = get_uptime()
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #f5f5f7;
                --card-bg: rgba(255, 255, 255, 0.82);
                --text: #1d1d1f;
                --text-secondary: #86868b;
                --accent: #0071e3;
                --success: #28cd41;
                --glass-border: rgba(255, 255, 255, 0.4);
            }}
            
            * {{ margin: 0; padding: 0; box-sizing: border-box; -webkit-font-smoothing: antialiased; }}
            
            body {{
                background-color: var(--bg);
                color: var(--text);
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
                min-height: 100vh;
                padding: 4vw;
                display: flex;
                flex-direction: column;
                background: radial-gradient(at 0% 0%, rgba(0, 113, 227, 0.05) 0px, transparent 50%),
                            radial-gradient(at 100% 100%, rgba(40, 205, 65, 0.05) 0px, transparent 50%);
            }}

            header {{
                margin-bottom: 3rem;
                display: flex;
                justify-content: space-between;
                align-items: flex-end;
            }}

            .greeting {{
                font-family: 'Outfit', sans-serif;
                font-size: clamp(2rem, 5vw, 3.5rem);
                font-weight: 700;
                letter-spacing: -0.04em;
                line-height: 1.1;
            }}

            .date {{
                color: var(--text-secondary);
                font-size: 1.1rem;
                font-weight: 500;
                margin-top: 0.5rem;
            }}

            .dashboard-grid {{
                display: grid;
                grid-template-columns: repeat(12, 1fr);
                grid-auto-rows: minmax(160px, auto);
                gap: 1.5rem;
                width: 100%;
                max-width: 1600px;
                margin: 0 auto;
            }}

            .bento-card {{
                background: var(--card-bg);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border);
                border-radius: 32px;
                padding: 2rem;
                transition: all 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                box-shadow: 0 8px 32px rgba(0,0,0,0.04);
                cursor: pointer;
                text-decoration: none;
                color: inherit;
            }}

            .bento-card:hover {{
                transform: scale(1.02);
                box-shadow: 0 20px 60px rgba(0,0,0,0.08);
                background: rgba(255, 255, 255, 0.95);
            }}

            /* Bento Sizes */
            .col-6 {{ grid-column: span 6; }}
            .col-4 {{ grid-column: span 4; }}
            .col-3 {{ grid-column: span 3; }}
            .row-2 {{ grid-row: span 2; }}

            @media (max-width: 1024px) {{
                .col-3 {{ grid-column: span 6; }}
                .col-4 {{ grid-column: span 6; }}
            }}
            @media (max-width: 768px) {{
                .col-6, .col-4, .col-3 {{ grid-column: span 12; }}
                body {{ padding: 6vw; }}
            }}

            .card-label {{
                font-size: 0.85rem;
                font-weight: 600;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                display: flex;
                align-items: center;
                gap: 8px;
            }}

            .card-value {{
                font-family: 'Outfit', sans-serif;
                font-size: 2.8rem;
                font-weight: 700;
                margin: 1rem 0;
                letter-spacing: -0.02em;
            }}

            .card-increment {{
                font-size: 0.95rem;
                font-weight: 600;
                color: var(--success);
            }}

            .icon-wrapper {{
                width: 56px;
                height: 56px;
                border-radius: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
                margin-bottom: 1.5rem;
            }}

            .btn-title {{ font-family: 'Outfit', sans-serif; font-size: 1.8rem; font-weight: 700; margin-bottom: 0.5rem; }}
            .btn-desc {{ color: var(--text-secondary); font-size: 1rem; line-height: 1.4; }}

            .status-dot {{
                width: 8px;
                height: 8px;
                background: var(--success);
                border-radius: 50%;
                display: inline-block;
                box-shadow: 0 0 12px var(--success);
                animation: pulse 2s infinite;
            }}

            @keyframes pulse {{
                0% {{ opacity: 1; }}
                50% {{ opacity: 0.5; }}
                100% {{ opacity: 1; }}
            }}

            .progress-bar {{
                width: 100%;
                height: 8px;
                background: rgba(0,0,0,0.05);
                border-radius: 4px;
                overflow: hidden;
                margin-top: 1rem;
            }}
            .progress-fill {{
                height: 100%;
                background: var(--accent);
                transition: width 1s ease-out;
            }}
        </style>
    </head>
    <body>
        <header>
            <div>
                <h2 class="date" id="currentDate"></h2>
                <h1 class="greeting">System Overview</h1>
            </div>
            <div class="card-label">
                <span class="status-dot"></span> LIVE STATUS
            </div>
        </header>

        <div class="dashboard-grid">
            <!-- Analytics Large Card -->
            <div class="bento-card col-6 row-2">
                <div class="card-label">Total Engagement</div>
                <div>
                   <div class="card-value" style="font-size: 5rem;">{visits}</div>
                   <div class="card-increment">↑ Increased interactions today</div>
                </div>
                <div class="btn-desc">Real-time visitor tracking powered by internal cache system.</div>
            </div>

            <!-- CPU Card -->
            <div class="bento-card col-3">
                <div class="card-label">CPU Usage</div>
                <div>
                    <div class="card-value">{cpu_usage}%</div>
                    <div class="progress-bar"><div class="progress-fill" style="width: {cpu_usage}%"></div></div>
                </div>
            </div>

            <!-- RAM Card -->
            <div class="bento-card col-3">
                <div class="card-label">Memory</div>
                <div>
                    <div class="card-value">{memory_usage}%</div>
                    <div class="progress-bar"><div class="progress-fill" style="width: {memory_usage}%"></div></div>
                </div>
            </div>

            <!-- Uptime Card -->
            <div class="bento-card col-3">
                <div class="card-label">Up Time</div>
                <div class="card-value" style="font-size: 2.2rem;">{uptime}</div>
            </div>

            <!-- Placeholder for future tool -->
            <div class="bento-card col-3" style="background: var(--accent); color: white; border: none;">
                <div class="card-label" style="color: rgba(255,255,255,0.7);">Efficiency</div>
                <div class="card-value" style="font-size: 2.2rem;">Optimal</div>
            </div>

            <!-- Menu: KFCC -->
            <a href="/kfcc" class="bento-card col-4 row-2">
                <div>
                    <div class="icon-wrapper" style="background: #eef6ff; color: #0071e3;">🏦</div>
                    <div class="btn-title">Financial<br>Inquiry</div>
                </div>
                <div class="btn-desc">Explore live interest rates from Geumgo branches nationwide.</div>
            </a>

            <!-- Menu: Cards -->
            <a href="/card-events" class="bento-card col-4 row-2">
                <div>
                    <div class="icon-wrapper" style="background: #fff1f0; color: #ff3b30;">💳</div>
                    <div class="btn-title">Promo<br>Explorer</div>
                </div>
                <div class="btn-desc">Stay updated with the latest credit card events and benefits.</div>
            </a>

            <!-- Placeholder Card -->
            <div class="bento-card col-4 row-2">
                <div>
                    <div class="icon-wrapper" style="background: #f2f2f7; color: #1d1d1f !important;">🚀</div>
                    <div class="btn-title">Future<br>Expansion</div>
                </div>
                <div class="btn-desc">New modules and AI-powered tools arriving soon.</div>
            </div>
        </div>

        <script>
            const d = new Date();
            const options = {{ weekday: 'long', month: 'long', day: 'numeric' }};
            document.getElementById('currentDate').innerText = d.toLocaleDateString('en-US', options).toUpperCase();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/card-events", response_class=HTMLResponse)
def card_events():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>카드사 이벤트 | Oracle Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; }

            .nav-header {
                position: sticky; top: 0; background: rgba(245, 245, 247, 0.8); backdrop-filter: blur(20px);
                z-index: 100; padding: 1rem; border-bottom: 1px solid var(--border-color);
            }

            .nav-content { max-width: 800px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            
            .main-content { max-width: 800px; margin: 3rem auto; padding: 0 1.5rem; text-align: center; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2.5rem; margin-bottom: 1rem; letter-spacing: -0.02em; }
            .subtitle { color: var(--text-secondary); margin-bottom: 3rem; font-weight: 300; }

            .card-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 1rem;
            }

            .card-link {
                background: white;
                border: 1px solid var(--border-color);
                border-radius: 16px;
                padding: 1rem;
                text-decoration: none;
                color: inherit;
                transition: all 0.2s ease;
                display: flex;
                flex-direction: column;
                align-items: center;
                box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            }

            .card-link:hover {
                transform: translateY(-8px);
                box-shadow: 0 20px 40px rgba(0,0,0,0.08);
                border-color: var(--blue-color);
            }

            .card-name { font-weight: 600; font-size: 1rem; color: #1d1d1f !important; text-align: center; }

            .search-box {
                background: white;
                border-radius: 16px;
                padding: 1rem 1.5rem;
                margin-bottom: 3rem;
                display: flex;
                align-items: center;
                border: 1px solid var(--border-color);
                box-shadow: 0 2px 8px rgba(0,0,0,0.02);
            }
            
            
            .search-box input {
                border: none;
                outline: none;
                width: 100%;
                font-size: 1rem;
                font-family: inherit;
                margin-left: 10px;
            }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 2rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 0.8rem;
            }

            .event-image {
                width: 100%;
                height: 120px;
                object-fit: cover;
                border-radius: 12px;
                margin-bottom: 1rem;
                background: #f5f5f7;
            }

            
            .tags-wrapper {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                align-items: center;
            }

            .company-tag {
                background: #1d1d1f; 
                color: white; 
                padding: 4px 8px; 
                border-radius: 6px; 
                font-weight: 600; 
                font-size: 0.7rem;
                letter-spacing: -0.01em;
            }
            .category-tag {
                background: #f5f5f7; 
                color: #6e6e73; 
                padding: 4px 8px; 
                border-radius: 6px; 
                font-weight: 600; 
                font-size: 0.7rem;
                letter-spacing: -0.01em;
            }
            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }

        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/" class="back-btn">← 대시보드</a>
                <div style="font-weight: 600;">카드사 이벤트 검색</div>
                <div style="width: 60px;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>혜택의 시작</h1>
            <p class="subtitle">국내 주요 카드사의 실시간 이벤트를 한눈에 확인하세요.</p>

            <div class="search-box">
                <span>🔍</span>
                <input type="text" id="cardSearch" placeholder="모든 카드사의 이벤트를 검색해보세요... (예: 할인, 캐시백, 포인트)" onkeyup="filterCards()">
            </div>


            <div class="card-grid" id="cardGrid">
                <a href="/card-events/shinhan" class="card-link" data-name="신한카드">
                    <div class="card-name">신한카드</div>
                </a>
                <a href="/card-events/samsung" class="card-link" data-name="삼성카드">
                    <div class="card-name">삼성카드</div>
                </a>
                <a href="/card-events/hyundai" class="card-link" data-name="현대카드">
                    <div class="card-name">현대카드</div>
                </a>
                <a href="/card-events/kb" class="card-link" data-name="KB국민카드">
                    <div class="card-name">KB국민카드</div>
                </a>
                <a href="/card-events/lotte" class="card-link" data-name="롯데카드">
                    <div class="card-name">롯데카드</div>
                </a>
                <a href="/card-events/woori" class="card-link" data-name="우리카드">
                    <div class="card-name">우리카드</div>
                </a>
                <a href="/card-events/hana" class="card-link" data-name="하나카드">
                    <div class="card-name">하나카드</div>
                </a>
                <a href="/card-events/bc" class="card-link" data-name="BC카드">
                    <div class="card-name">BC카드</div>
                </a>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }
            
            async function fetchAllEvents() {
                try {
                    const [shinhanRes, kbRes, hanaRes, wooriRes, bcRes, samsungRes, hyundaiRes, lotteRes] = await Promise.all([
                        fetch('/api/shinhan-cards'),
                        fetch('/api/kb-cards'),
                        fetch('/api/hana-cards'),
                        fetch('/api/woori-cards'),
                        fetch('/api/bc-cards'),
                        fetch('/api/samsung-cards'),
                        fetch('/api/hyundai-cards'),
                        fetch('/api/lotte-cards')
                    ]);
                    
                    const shinhanData = await shinhanRes.json();
                    const kbData = await kbRes.json();
                    const hanaData = await hanaRes.json();
                    const wooriData = await wooriRes.json();
                    const bcData = await bcRes.json();
                    const samsungData = await samsungRes.json();
                    const hyundaiData = await hyundaiRes.json();
                    const lotteData = await lotteRes.json();

                    // 회사별 색상 매핑
                    const companyColors = {
                        "신한카드": { bg: "#0046ff", text: "white" },
                        "KB국민카드": { bg: "#ffbc00", text: "#3d3d3d" }, // KB는 노란색이라 글자 검정
                        "하나카드": { bg: "#009490", text: "white" },
                        "우리카드": { bg: "#007bc3", text: "white" },
                        "BC카드": { bg: "#ed1c24", text: "white" },
                        "삼성카드": { bg: "#0056b3", text: "white" },
                        "현대카드": { bg: "#000000", text: "white" },
                        "롯데카드": { bg: "#ed1c24", text: "white" }
                    };

                    const normalize = (data, company) => {
                        const list = Array.isArray(data) ? data : (data.data || []);
                        const colorInfo = companyColors[company] || { bg: "#1d1d1f", text: "white" };
                        
                        return list.map(item => ({ 
                            ...item, 
                            companyName: company,
                            tagBg: colorInfo.bg,
                            tagColor: colorInfo.text
                        }));
                    };

                    const shinhan = normalize(shinhanData, "신한카드");
                    const kb = normalize(kbData, "KB국민카드");
                    const hana = normalize(hanaData, "하나카드");
                    const woori = normalize(wooriData, "우리카드");
                    const bc = normalize(bcData, "BC카드");
                    const samsung = normalize(samsungData, '삼성카드');
                    const hyundai = normalize(hyundaiData, '현대카드');
                    const lotte = normalize(lotteData, '롯데카드');

                    allEvents = [...shinhan, ...kb, ...hana, ...woori, ...bc, ...samsung, ...hyundai, ...lotte];
                    
                    const searchInput = document.getElementById('cardSearch');
                    if(searchInput.value.trim().length > 0) {
                        searchEvents(searchInput.value.trim().toLowerCase());
                    }
                } catch (error) {
                    console.error('Failed to fetch events:', error);
                }
            }

            function filterCards() {
                const search = document.getElementById('cardSearch').value.toLowerCase();
                if (search.length === 0) { showCards(); return; }
                if (allEvents.length === 0) { fetchAllEvents().then(() => searchEvents(search)); }
                else { searchEvents(search); }
            }

            function showCards() {
                document.getElementById('cardGrid').style.display = 'grid';
                const eventList = document.getElementById('eventList');
                if (eventList) eventList.style.display = 'none';
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")+" "+(ev.companyName||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }

            function searchEvents(search) {
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                
                document.getElementById('cardGrid').style.display = 'none';
                
                let eventList = document.getElementById('eventList');
                if (!eventList) {
                    eventList = document.createElement('div');
                    eventList.id = 'eventList';
                    eventList.className = 'event-list';
                    document.querySelector('.main-content').appendChild(eventList);
                } else {
                    eventList.className = 'event-list';
                    // 기존 인라인 스타일 제거 (중요)
                    eventList.style.display = 'grid'; 
                    eventList.style.cssText = ''; 
                    eventList.style.display = 'grid';
                }
                eventList.style.display = 'grid';
                
                if (filtered.length === 0) {
                    eventList.innerHTML = '<div class="loading">검색 결과가 없습니다.</div>';
                    return;
                }

                eventList.innerHTML = filtered.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        <div class="event-category-row">
                            <div class="tags-wrapper">
                                <span class="company-tag" style="background:${ev.tagBg}; color:${ev.tagColor}">${ev.companyName}</span>
                                <span class="category-tag">${ev.category}</span>
                            </div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }

            fetchAllEvents();
</script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/card-events/kb", response_class=HTMLResponse)
def kb_card_events():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>KB국민카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
                --kb-color: #ffbc00;
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; }

            .nav-header {
                position: sticky; top: 0; background: rgba(245, 245, 247, 0.8); backdrop-filter: blur(20px);
                z-index: 100; padding: 1rem; border-bottom: 1px solid var(--border-color);
            }

            .nav-content { max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            
            .main-content { max-width: 1400px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 1.5rem; }

            
            
            
            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }
            .search-input {
                flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem;
            }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 1rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
            }
            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }



        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    KB국민카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>KB국민카드 이벤트 검색</h1>
            
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>

            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                try {
                    await fetch('/api/kb/update', {method:'POST'});
                    alert('데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.');
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/kb-cards');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }


            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            
            
            
            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }




            fetchEvents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/card-events/hana", response_class=HTMLResponse)
def hana_card_events():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>하나카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
                --kb-color: #008485;
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; }

            .nav-header {
                position: sticky; top: 0; background: rgba(245, 245, 247, 0.8); backdrop-filter: blur(20px);
                z-index: 100; padding: 1rem; border-bottom: 1px solid var(--border-color);
            }

            .nav-content { max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            
            .main-content { max-width: 1400px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 1.5rem; }

            
            
            
            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }
            .search-input {
                flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem;
            }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 1rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
            }
            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }



        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    하나카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>하나카드 이벤트 검색</h1>
            
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>

            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/hana-cards');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            
            
            
            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }




            fetchEvents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/card-events/shinhan", response_class=HTMLResponse)
def shinhan_card_events():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>신한카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
                --sh-color: #0046ff;
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; }

            .nav-header {
                position: sticky; top: 0; background: rgba(245, 245, 247, 0.8); backdrop-filter: blur(20px);
                z-index: 100; padding: 1rem; border-bottom: 1px solid var(--border-color);
            }

            .nav-content { max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            
            .main-content { max-width: 1400px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 0.5rem; }
            .official-link { display: inline-block; margin-bottom: 1.5rem; color: var(--sh-color); text-decoration: none; font-size: 0.9rem; font-weight: 500; }
            .official-link:hover { text-decoration: underline; }

            
            
            
            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }
            .search-input {
                flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem;
            }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 1rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 0.8rem;
            }

            .event-image {
                width: 100%;
                height: 120px;
                object-fit: cover;
                border-radius: 12px;
                margin-bottom: 1rem;
                background: #f5f5f7;
            }

            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }



        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    신한카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>신한카드 이벤트 검색</h1>
            
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="이벤트 또는 마이샵 쿠폰을 검색해보세요..." onkeyup="filterEvents()">
            </div>

            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const [eventsRes, myshopRes] = await Promise.all([
                        fetch('/api/shinhan-cards'),
                        fetch('/api/shinhan-myshop')
                    ]);
                    
                    const eventsData = await eventsRes.json();
                    const myshopData = await myshopRes.json();
                    
                    if(eventsData.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${eventsData.last_updated.substring(5,16)}`;
                    
                    const events = Array.isArray(eventsData) ? eventsData : (eventsData.data || []);
                    const myshop = Array.isArray(myshopData) ? myshopData : (myshopData.data || []);
                    
                    allEvents = [...events, ...myshop];
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }



            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            
            
            
            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        
                        
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }




            fetchEvents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/health")
def health_check():
    return {"status": "ok"}
# 우리카드 크롤러 (Playwright API 가로채기 - 최적화)
async def crawl_woori_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Woori background crawl (Playwright)...")
        from playwright.async_api import async_playwright
        
        all_events = []
        base_url = "https://m.wooricard.com"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                viewport={'width': 375, 'height': 812}
            )
            page = await context.new_page()
            
            captured_json = None
            
            async def handle_response(response):
                nonlocal captured_json
                if "getPrgEvntList.pwkjson" in response.url and response.status == 200:
                    try:
                        captured_json = await response.json()
                    except: pass
            
            page.on("response", handle_response)

            try:
                # API 호출을 기다림 (타임아웃 30초)
                request_promise = page.wait_for_response(lambda res: "getPrgEvntList.pwkjson" in res.url and res.status == 200, timeout=30000)
                
                await page.goto("https://m.wooricard.com/dcmw/yh1/bnf/bnf02/prgevnt/M1BNF202S00.do")
                
                response = await request_promise
                json_data = await response.json()
                
                if json_data:
                    events = json_data.get('prgEvntList', [])
                    print(f"Woori API captured with {len(events)} events")
                    
                    seen_titles = set()
                    for ev in events:
                        title = (ev.get('cardEvntNm', '') or ev.get('mblDocTitlTxt', '')).strip()
                        if not title or title in seen_titles: continue
                        seen_titles.add(title)

                        start_date = ev.get('evntSdt', '')
                        end_date = ev.get('evntEdt', '')
                        
                        if len(start_date) == 8: start_date = f"{start_date[:4]}.{start_date[4:6]}.{start_date[6:]}"
                        if len(end_date) == 8: end_date = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:]}"
                        period = f"{start_date} ~ {end_date}" if start_date and end_date else ""
                        
                        img_path = ev.get('fileCoursWeb', '')
                        if img_path and not img_path.startswith('http'): 
                            img_path = f"{base_url}{img_path}"
                        
                        # 사용자가 제공한 PC 상세 링크 패턴 적용
                        evnt_srno = ev.get('evntSrno', '')
                        if evnt_srno:
                            link = f"https://pc.wooricard.com/dcpc/yh1/bnf/bnf02/prgevnt/H1BNF202S01.do?evntSrno={evnt_srno}"
                        else:
                            link = "https://m.wooricard.com/dcmw/yh1/bnf/bnf02/prgevnt/M1BNF202S00.do"
                        
                        all_events.append({
                            "category": "우리카드",
                            "eventName": title,
                            "period": period,
                            "link": link,
                            "image": img_path,
                            "bgColor": "#007bc3"
                        })
                            
            except Exception as e:
                print(f"Woori API wait failed, trying captured data: {e}")
                if captured_json:
                    events = captured_json.get('prgEvntList', [])
                    seen_titles = set()
                    for ev in events:
                        title = ev.get('cardEvntNm', '').strip()
                        if not title or title in seen_titles: continue
                        seen_titles.add(title)

                        img_path = ev.get('fileCoursWeb', '')
                        if img_path and not img_path.startswith('http'): img_path = f"{base_url}{img_path}"
                        all_events.append({
                            "category": "우리카드",
                            "eventName": title,
                            "period": "",
                            "link": base_url,
                            "image": img_path,
                            "bgColor": "#007bc3"
                        })
            finally:
                await browser.close()
                
        if all_events:
            try:
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("woori_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                if r: r.setex(WOORI_CACHE_KEY, CACHE_EXPIRE, json.dumps(output_data))
                print(f"[{datetime.now(seoul_tz)}] Woori crawl finished. {len(all_events)} events.")
            except Exception as fe: print(f"Woori save failed: {fe}")
        else:
            print(f"[{datetime.now(seoul_tz)}] Woori crawl finished but no events found.")
            
    except Exception as e:
        print(f"Woori crawl failed: {e}")


# BC카드 크롤러 (실제 API 사용 - 복원)
async def crawl_bc_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting BC background crawl...")
        all_events = []
        seen_titles = set()
        base_url = "https://web.paybooc.co.kr"
        api_url = f"{base_url}/web/evnt/lst-evnt-data"
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            headers = {
                "Referer": "https://web.paybooc.co.kr/web/evnt/main",
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            }
            
            for page in range(1, 10):
                params = {"reqType": "init" if page == 1 else "more", "inqrDv": "ING", "pgeNo": str(page), "pgeCnt": "20", "ordering": "RECENT"}
                try:
                    response = await client.get(api_url, params=params, headers=headers)
                    if response.status_code != 200: break
                    data = response.json()
                    event_list = data.get("data", {}).get("evntInqrList", [])
                    if not event_list: break
                    
                    for ev in event_list:
                        title_parts = [ev.get("pybcUnifEvntNm1", ""), ev.get("pybcUnifEvntNm2", ""), ev.get("pybcUnifEvntNm3", "")]
                        title = " ".join([p for p in title_parts if p]).strip()
                        
                        if not title or title in seen_titles: continue
                        seen_titles.add(title)

                        start_date = ev.get("evntBltnStrtDtm", "")
                        end_date = ev.get("evntBltnEndDtm", "")
                        if len(start_date) >= 8: start_date = f"{start_date[:4]}.{start_date[4:6]}.{start_date[6:8]}"
                        if len(end_date) >= 8: end_date = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:8]}"
                        period = f"{start_date} ~ {end_date}" if start_date and end_date else ""
                        
                        img_url = ev.get("evntBsImgUrlAddr", "")
                        event_no = ev.get("pybcUnifEvntNo", "")
                        link = f"{base_url}/web/evnt/evnt-dts?pybcUnifEvntNo={event_no}" if event_no else f"{base_url}/web/evnt/main"
                        bg_color = ev.get("evntBsBgColrVal", "#ffffff")
                        
                        all_events.append({
                            "category": "BC카드",
                            "eventName": title,
                            "period": period,
                            "link": link,
                            "image": img_url,
                            "bgColor": bg_color
                        })
                except Exception: break
        
        if all_events:
            try:
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("bc_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                if r: r.setex(BC_CACHE_KEY, CACHE_EXPIRE, json.dumps(output_data))
                print(f"[{datetime.now(seoul_tz)}] BC crawl finished. {len(all_events)} events.")
            except Exception as fe: print(f"BC file save failed: {fe}")
    except Exception as e:
        print(f"[{datetime.now(seoul_tz)}] BC crawl failed: {e}")


# 삼성카드 크롤러 (Playwright - cms_id 기반 직접 링크 지원)
async def crawl_samsung_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Samsung background crawl (Playwright Mobile)...")
        from playwright.async_api import async_playwright
        
        all_events = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 375, 'height': 812})
            page = await context.new_page()
            
            try:
                # 목록 페이지 접속
                await page.goto("https://m.samsungcard.com/personal/event/ing/UHPPBE1401M0.jsp", timeout=60000)
                await page.wait_for_timeout(8000)
                
                # DOM 파싱
                events_data = await page.evaluate('''() => {
                    const results = [];
                    document.querySelectorAll('li').forEach(li => {
                        const img = li.querySelector('img');
                        const a = li.querySelector('a');
                        
                        if (!img || !a) return;
                        
                        let text = li.innerText.replace(/[\n\r]+/g, ' ').trim();
                        const dateMatch = text.match(/(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{4}\.\d{2}\.\d{2})/);
                        
                        // onclick 속성에서 ID 추출
                        const onclick = a.getAttribute('onclick') || "";
                        const idMatch = onclick.match(/GoDtlBrws\(['"](\d+)['"]/);
                        const cmsId = idMatch ? idMatch[1] : "";
                        
                        if (dateMatch && cmsId) {
                            let period = dateMatch[0];
                            // 제목 정제
                            let title = text.replace(/좋아요\s*갯수\s*\d+/, '').replace(period, '').trim();
                            if(title.length > 100) title = title.substring(0, 100);
                            
                            results.push({
                                eventName: title,
                                period: period,
                                image: img.src,
                                cmsId: cmsId
                            });
                        }
                    });
                    return results;
                }''')
                
                if events_data:
                    for ev in events_data:
                        cms_id = ev.get('cmsId')
                        # 사용자가 요청한 상세 페이지 직접 링크
                        link = f"https://www.samsungcard.com/personal/event/ing/UHPPBE1403M0.jsp?cms_id={cms_id}"
                        
                        all_events.append({
                            "category": "삼성카드",
                            "eventName": ev['eventName'],
                            "period": ev['period'],
                            "link": link,
                            "image": ev['image'],
                            "bgColor": "#0056b3"
                        })

            except Exception as e:
                print(f"Samsung Playwright error: {e}")
            finally:
                await browser.close()

        if all_events:
            try:
                unique_events = {v['eventName']:v for v in all_events}.values()
                all_events = list(unique_events)
                
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("samsung_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                if r: r.setex(SAMSUNG_CACHE_KEY, CACHE_EXPIRE, json.dumps(output_data))
                print(f"[{datetime.now(seoul_tz)}] Samsung crawl finished. {len(all_events)} events.")
            except Exception as e:
                print(f"Samsung save failed: {e}")
        else:
            print(f"[{datetime.now(seoul_tz)}] Samsung crawl finished but no events found.")

    except Exception as e:
        print(f"Samsung crawl failed: {e}")


# 현대카드 크롤러
async def crawl_hyundai_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Hyundai background crawl...")
        from playwright.async_api import async_playwright
        all_events = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto("https://www.hyundaicard.com/cpb/ev/CPBEV0101_01.hc", timeout=60000)
                await page.wait_for_timeout(8000)
                events_data = await page.evaluate('''() => {
                    const results = [];
                    document.querySelectorAll('li').forEach(li => {
                        const img = li.querySelector('img');
                        let text = li.innerText.replace(/[\n\r]+/g, ' ').trim();
                        // 날짜 패턴 (공백 유연하게)
                        const dateMatch = text.match(/(\d{4}\.\s*\d{1,2}\.\s*\d{1,2})\s*~\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2})/);
                        if (dateMatch && img) {
                            let period = dateMatch[0];
                            let title = text.replace(period, '').trim();
                            if(title.length > 100) title = title.substring(0, 100);
                            const linkEl = li.querySelector('a');
                            results.push({
                                eventName: title,
                                period: period,
                                image: img.src,
                                link: linkEl ? linkEl.href : ""
                            });
                        }
                    });
                    return results;
                }''')
                for ev in events_data:
                    title = ev.get('eventName', '').strip()
                    if not title or any(x['eventName'] == title for x in all_events): continue
                    
                    link = ev['link']
                    if not link or "javascript" in link:
                        link = "https://www.hyundaicard.com/cpb/ev/CPBEV0101_01.hc"
                    all_events.append({
                        "category": "현대카드",
                        "eventName": title,
                        "period": ev['period'],
                        "link": link,
                        "image": ev['image'],
                        "bgColor": "#000000"
                    })
            except Exception as e: print(f"Hyundai Playwright error: {e}")
            finally: await browser.close()
        if all_events:
            try:
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("hyundai_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                if r: r.setex("events:hyundai", CACHE_EXPIRE, json.dumps(output_data))
                print(f"[{datetime.now(seoul_tz)}] Hyundai crawl finished. {len(all_events)} events.")
            except Exception as e: print(f"Hyundai save failed: {e}")
    except Exception as e: print(f"Hyundai crawl failed: {e}")



# 롯데카드 크롤러
async def crawl_lotte_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Lotte background crawl...")
        from playwright.async_api import async_playwright
        all_events = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 375, 'height': 812})
            page = await context.new_page()
            try:
                await page.goto("https://m.lottecard.co.kr/app/LPBNFDA_V100.lc", timeout=60000)
                await page.wait_for_timeout(10000)
                events_data = await page.evaluate('''() => {
                    const results = [];
                    document.querySelectorAll('li').forEach(li => {
                        const img = li.querySelector('img');
                        let text = li.innerText.replace(/[\n\r]+/g, ' ').trim();
                        // 날짜: YYYY.MM.DD ~ YYYY.MM.DD
                        const dateMatch = text.match(/(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{4}\.\d{2}\.\d{2})/);
                        if (dateMatch && img) {
                            let period = dateMatch[0];
                            let title = text.replace(period, '').trim();
                            if(title.length > 100) title = title.substring(0, 100);
                            const linkEl = li.querySelector('a');
                            results.push({
                                eventName: title,
                                period: period,
                                image: img.src,
                                link: linkEl ? linkEl.href : ""
                            });
                        }
                    });
                    return results;
                }''')
                for ev in events_data:
                    link = ev['link']
                    if not link or "javascript" in link:
                        link = "https://m.lottecard.co.kr/app/LPBNFDA_V100.lc"
                    all_events.append({
                        "category": "롯데카드",
                        "eventName": ev['eventName'],
                        "period": ev['period'],
                        "link": link,
                        "image": ev['image'],
                        "bgColor": "#ed1c24"
                    })
            except Exception as e: print(f"Lotte Playwright error: {e}")
            finally: await browser.close()
        if all_events:
            try:
                unique = {v['eventName']:v for v in all_events}.values()
                all_events = list(unique)
                output_data = {"last_updated": datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}
                with open("lotte_data.json", "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False)
                if r: r.setex("events:lotte", CACHE_EXPIRE, json.dumps(output_data))
                print(f"[{datetime.now(seoul_tz)}] Lotte crawl finished. {len(all_events)} events.")
            except Exception as e: print(f"Lotte save failed: {e}")
        else:
            print(f"[{datetime.now(seoul_tz)}] Lotte crawl finished but no events found.")
    except Exception as e: print(f"Lotte crawl failed: {e}")


@app.get("/api/hyundai-cards")
def get_hyundai_cards():
    return get_cached_data("events:hyundai", "hyundai_data.json")

@app.post("/api/hyundai/update")
async def update_hyundai(background_tasks: BackgroundTasks):
    background_tasks.add_task(crawl_hyundai_bg)
    return {"status": "started"}


@app.get("/api/lotte-cards")
def get_lotte_cards():
    return get_cached_data("events:lotte", "lotte_data.json")

@app.post("/api/lotte/update")
async def update_lotte(background_tasks: BackgroundTasks):
    background_tasks.add_task(crawl_lotte_bg)
    return {"status": "started"}

@app.get("/api/woori-cards")
async def get_woori_cards():
    return get_cached_data(WOORI_CACHE_KEY, 'woori_data.json')

@app.post("/api/woori/update")
async def update_woori(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_woori_bg)
    return {"status": "started"}

# BC카드 API 엔드포인트
@app.get("/api/bc-cards")
async def get_bc_cards():
    return get_cached_data(BC_CACHE_KEY, 'bc_data.json')

@app.post("/api/bc/update")
async def update_bc(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_bc_bg)
    return {"status": "started"}

# 삼성카드 API 엔드포인트
@app.get("/api/samsung-cards")
async def get_samsung_cards():
    return get_cached_data(SAMSUNG_CACHE_KEY, 'samsung_data.json')

@app.post("/api/samsung/update")
async def update_samsung(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_samsung_bg)
    return {"status": "started"}

@app.get("/card-events/woori", response_class=HTMLResponse)
def woori_card_events():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>우리카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; margin: 0; }

            .nav-header {
                position: sticky; top: 0; background: rgba(255,255,255,0.8); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                border-bottom: 1px solid var(--border-color); z-index: 100;
            }
            .nav-content {
                max-width: 1400px; margin: 0 auto; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center;
            }
            .back-btn {
                color: var(--blue-color); text-decoration: none; font-weight: 500; font-size: 0.95rem;
            }

            .main-content { max-width: 1400px; margin: 0 auto; padding: 2rem 1.5rem; }
            h1 { font-size: 2.5rem; font-weight: 600; margin-bottom: 1rem; }
            
            
            
            
            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }
            .search-input {
                flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem;
            }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 1rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
            }
            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }



        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    우리카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>우리카드 이벤트 검색</h1>
            
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>

            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/woori-cards');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            
            
            
            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        
                        
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }




            fetchEvents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/card-events/bc", response_class=HTMLResponse)
def bc_card_events():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BC카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; margin: 0; }

            .nav-header {
                position: sticky; top: 0; background: rgba(255,255,255,0.8); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                border-bottom: 1px solid var(--border-color); z-index: 100;
            }
            .nav-content {
                max-width: 1400px; margin: 0 auto; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center;
            }
            .back-btn {
                color: var(--blue-color); text-decoration: none; font-weight: 500; font-size: 0.95rem;
            }

            .main-content { max-width: 1400px; margin: 0 auto; padding: 2rem 1.5rem; }
            h1 { font-size: 2.5rem; font-weight: 600; margin-bottom: 1rem; }
            
            
            
            
            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }
            .search-input {
                flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem;
            }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 1rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
            }
            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }



        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    BC카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>BC카드 이벤트 검색</h1>
            
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>

            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/bc-cards');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            
            
            
            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }




            fetchEvents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/card-events/samsung", response_class=HTMLResponse)
def samsung_card_events():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>삼성카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; margin: 0; }

            .nav-header {
                position: sticky; top: 0; background: rgba(255,255,255,0.8); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                border-bottom: 1px solid var(--border-color); z-index: 100;
            }
            .nav-content {
                max-width: 1400px; margin: 0 auto; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center;
            }
            .back-btn {
                color: var(--blue-color); text-decoration: none; font-weight: 500; font-size: 0.95rem;
            }

            .main-content { max-width: 1400px; margin: 0 auto; padding: 2rem 1.5rem; }
            h1 { font-size: 2.5rem; font-weight: 600; margin-bottom: 1rem; }
            
            
            
            
            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }
            .search-input {
                flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem;
            }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 1rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
            }
            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }



        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    삼성카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>삼성카드 이벤트 검색</h1>
            
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>

            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/samsung-cards');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            
            
            
            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }




            fetchEvents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/card-events/search", response_class=HTMLResponse)
def card_events_search():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>통합 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; margin: 0; }

            .nav-header {
                position: sticky; top: 0; background: rgba(255,255,255,0.8); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                border-bottom: 1px solid var(--border-color); z-index: 100;
            }
            .nav-content {
                max-width: 1400px; margin: 0 auto; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center;
            }
            .back-btn {
                color: var(--blue-color); text-decoration: none; font-weight: 500; font-size: 0.95rem;
            }

            .main-content { max-width: 1400px; margin: 0 auto; padding: 2rem 1.5rem; }
            h1 { font-size: 2.5rem; font-weight: 600; margin-bottom: 1rem; }
            
            
            
            
            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }
            .search-input {
                flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem;
            }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                gap: 1.25rem; 
                margin-top: 1rem; 
            }
            .event-card {
                background: white; 
                border-radius: 18px; 
                padding: 1.5rem; 
                display: flex; 
                flex-direction: column; 
                justify-content: space-between;
                border: 1px solid rgba(0,0,0,0.08); 
                text-decoration: none; 
                color: inherit; 
                transition: all 0.2s ease;
                height: 100%;
                min-height: 180px;
                position: relative;
                box-sizing: border-box;
            }
            .event-card:hover { 
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.06);
                border-color: rgba(0,0,0,0.12);
            }
            
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
            }
            
            .event-title {
                font-size: 1.05rem;
                font-weight: 700;
                color: #1d1d1f !important;
                margin-bottom: 1rem;
                line-height: 1.45;
                letter-spacing: -0.01em;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                word-break: keep-all;
                flex: 1;
             }
            
            .event-date {
                font-size: 0.8rem;
                color: #86868b;
                letter-spacing: -0.01em;
                margin-top: auto;
            }
            
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }



        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600;">전체 이벤트 통합 검색</div>
                <div style="width: 80px;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>모든 카드사 이벤트 검색</h1>
            
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="모든 카드사의 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>

            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    // 모든 카드사 API 호출
                    const [shinhanRes, kbRes, hanaRes, wooriRes, bcRes, samsungRes, hyundaiRes, lotteRes] = await Promise.all([
                        fetch('/api/shinhan-cards'),
                        fetch('/api/kb-cards'),
                        fetch('/api/hana-cards'),
                        fetch('/api/woori-cards'),
                        fetch('/api/bc-cards'),
                        fetch('/api/samsung-cards'),
                        fetch('/api/hyundai-cards'),
                        fetch('/api/lotte-cards')
                    ]);
                    
                    const shinhanData = await shinhanRes.json();
                    const kbData = await kbRes.json();
                    const hanaData = await hanaRes.json();
                    const wooriData = await wooriRes.json();
                    const bcData = await bcRes.json();
                    const samsungData = await samsungRes.json();
                    const hyundaiData = await hyundaiRes.json();
                    const lotteData = await lotteRes.json();

                    const shinhan = Array.isArray(shinhanData) ? shinhanData : (shinhanData.data || []);
                    const kb = Array.isArray(kbData) ? kbData : (kbData.data || []);
                    const hana = Array.isArray(hanaData) ? hanaData : (hanaData.data || []);
                    const woori = Array.isArray(wooriData) ? wooriData : (wooriData.data || []);
                    const bc = Array.isArray(bcData) ? bcData : (bcData.data || []);
                    const samsung = Array.isArray(samsungData) ? samsungData : (samsungData.data || []);

                    allEvents = [...shinhan, ...kb, ...hana, ...woori, ...bc, ...samsung, ...hyundai, ...lotte];
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            
            
            
            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }




            fetchEvents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/card-events/hyundai", response_class=HTMLResponse)
def hyundai_cards_page():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>현대카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; }
            .nav-header { position: sticky; top: 0; background: rgba(245, 245, 247, 0.8); backdrop-filter: blur(20px); z-index: 100; padding: 1rem; border-bottom: 1px solid var(--border-color); }
            .nav-content { max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            .main-content { max-width: 1400px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 1.5rem; }
            .search-section { display: flex; gap: 1rem; margin-bottom: 2rem; }
            .search-input { flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color); box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem; }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }
            .event-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1.25rem; margin-top: 1rem; }
            .event-card { background: white; border-radius: 18px; padding: 1.5rem; display: flex; flex-direction: column; justify-content: space-between; border: 1px solid rgba(0,0,0,0.08); text-decoration: none; color: inherit; transition: all 0.2s ease; height: 100%; min-height: 180px; position: relative; box-sizing: border-box; }
            .event-card:hover { transform: translateY(-4px); box-shadow: 0 8px 20px rgba(0,0,0,0.06); border-color: rgba(0,0,0,0.12); }
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row { width: 100%; display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
            .event-title { font-size: 1.05rem; font-weight: 700; color: #1d1d1f !important; margin-bottom: 1rem; line-height: 1.45; letter-spacing: -0.01em; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; word-break: keep-all; flex: 1; }
            .event-date { font-size: 0.8rem; color: #86868b; letter-spacing: -0.01em; margin-top: auto; }
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }
        </style>
    </head>

    
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    현대카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>
        <div class="main-content">
            <h1>현대카드 이벤트 검색</h1>
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>
            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

    
        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/hyundai-cards');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                stats.innerText = `총 ${events.length}개의 이벤트`;
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }
                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }
            fetchEvents();
        </script>

    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/card-events/lotte", response_class=HTMLResponse)
def lotte_cards_page():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>롯데카드 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; }
            .nav-header { position: sticky; top: 0; background: rgba(245, 245, 247, 0.8); backdrop-filter: blur(20px); z-index: 100; padding: 1rem; border-bottom: 1px solid var(--border-color); }
            .nav-content { max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            .main-content { max-width: 1400px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 1.5rem; }
            .search-section { display: flex; gap: 1rem; margin-bottom: 2rem; }
            .search-input { flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color); box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem; }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }
            .event-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1.25rem; margin-top: 1rem; }
            .event-card { background: white; border-radius: 18px; padding: 1.5rem; display: flex; flex-direction: column; justify-content: space-between; border: 1px solid rgba(0,0,0,0.08); text-decoration: none; color: inherit; transition: all 0.2s ease; height: 100%; min-height: 180px; position: relative; box-sizing: border-box; }
            .event-card:hover { transform: translateY(-4px); box-shadow: 0 8px 20px rgba(0,0,0,0.06); border-color: rgba(0,0,0,0.12); }
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row { width: 100%; display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
            .event-title { font-size: 1.05rem; font-weight: 700; color: #1d1d1f !important; margin-bottom: 1rem; line-height: 1.45; letter-spacing: -0.01em; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; word-break: keep-all; flex: 1; }
            .event-date { font-size: 0.8rem; color: #86868b; letter-spacing: -0.01em; margin-top: auto; }
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }
        </style>
    </head>

    
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    롯데카드 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>
        <div class="main-content">
            <h1>롯데카드 이벤트 검색</h1>
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>
            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>

    
        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/lotte-cards');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                stats.innerText = `총 ${events.length}개의 이벤트`;
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }
                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display='none'">` : ""}
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }
            fetchEvents();
        </script>

    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
