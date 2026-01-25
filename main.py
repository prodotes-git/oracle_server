import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
import os
import redis
import psutil
import time
from datetime import datetime
import json
import ssl

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
SHINHAN_MYSHOP_CACHE_KEY = "shinhan_myshop_cache_v3" # 안정성 강화를 위한 v3
WOORI_CACHE_KEY = "woori_card_events_cache_v1"
BC_CACHE_KEY = "bc_card_events_cache_v1"
SAMSUNG_CACHE_KEY = "samsung_card_events_cache_v1"
CACHE_EXPIRE = 3600  # 1시간 동안 캐시 유지

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
                            "eventName": f"[{name}] {benefit}",
                            "period": end,
                            "link": link,
                            "image": img,
                            "bgColor": "#ffffff"
                        })
                else:
                    print(f"Shinhan MyShop API returned message: {msg}")

        if all_coupons:
            try:
                r.setex(SHINHAN_MYSHOP_CACHE_KEY, CACHE_EXPIRE, json.dumps(all_coupons))
            except Exception: pass
            
        return all_coupons
    except Exception as e:
        print(f"Shinhan MyShop API Error: {e}")
        return []
    except Exception as e:
        print(f"Shinhan MyShop API Error: {e}")
        return []

# 신한카드 데이터 갱신 (백그라운드)
async def crawl_shinhan_bg():
    try:
        print(f"[{datetime.now()}] Starting Shinhan background crawl...")
        all_events = []
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

                        title = ev.get('mobWbEvtNm', '')
                        sub_title = ev.get('evtImgSlTilNm', '')
                        if sub_title and sub_title != title:
                            title = f"{sub_title} {title}"
                            
                        all_events.append({
                            "category": ev.get('hpgEvtKindNm', '이벤트'),
                            "eventName": title.strip(),
                            "period": f"{start} ~ {end}",
                            "link": link_url,
                            "image": img_url,
                            "bgColor": "#ffffff"
                        })
                except Exception: continue

        if all_events:
            try:
                with open("shinhan_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"Shinhan file save failed: {fe}")

            if r:
                try:
                    r.setex(SHINHAN_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                    print(f"Shinhan Redis save failed: {re}")

            print(f"[{datetime.now()}] Shinhan crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] Shinhan crawl failed: {e}")

# KB카드 데이터 갱신 (백그라운드)
# KB카드 데이터 갱신 (백그라운드)
async def crawl_kb_bg():
    try:
        print(f"[{datetime.now()}] Starting KB background crawl...")
        all_events = []
        seen_ids = set()
        
        api_url = "https://m.kbcard.com/BON/API/MBBACXHIABNC0064"
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            for page in range(1, 40): 
                payload = {"pageCount": page, "evtName": "", "evntStatus": "", "evntBonTag": "", "evntScp": ""}
                headers = {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "User-Agent": "Mozilla/5.0"}
                try:
                    response = await client.post(api_url, data=payload, headers=headers)
                    if response.status_code != 200: break
                    res_json = response.json()
                    events = res_json.get("evntList", [])
                    if not events: break
                    
                    for ev in events:
                        evt_no = ev.get('evtNo', '')
                        if not evt_no or evt_no in seen_ids: continue
                        seen_ids.add(evt_no)
                        
                        cat = ev.get("evntBonContents", "")
                        cat_map = {"01": "포인트/캐시백", "02": "할인/무이자", "03": "경품", "04": "기타"}
                        category = cat_map.get(cat, "이벤트")
                        
                        img = ev.get('evtImgPath', '')
                        if img and not img.startswith('http'): img = f"https://img1.kbcard.com/ST/img/cxc{img}"
                        
                        link = f"https://m.kbcard.com/BON/DVIEW/MBBMCXHIABNC0026?evntSerno={evt_no}&evntMain=Y"
                        
                        all_events.append({
                            "category": category,
                            "eventName": f"{ev.get('evtNm', '')} {ev.get('evtSubNm', '')}".strip(),
                            "period": ev.get("evtYMD", ""),
                            "link": link,
                            "image": img,
                            "bgColor": "#ffffff"
                        })
                    
                    if page >= int(res_json.get("totalPageCount", 0)): break
                except: break
        
        if all_events:
            with open("kb_data.json", "w", encoding="utf-8") as f: json.dump(all_events, f, ensure_ascii=False)
            if r: r.setex("kb_card_events_cache_v1", 3600, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
            print(f"[{datetime.now()}] KB Updated: {len(all_events)}")
    except Exception as e: print(e)


@app.get("/api/shinhan-cards")
async def get_shinhan_cards():
    try:
        import json
        if r:
            cached = r.get(SHINHAN_CACHE_KEY)
            if cached: return json.loads(cached)

        local_path = "shinhan_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            response = {"last_updated": last_updated, "data": data}
            if r:
                try:
                    r.setex(SHINHAN_CACHE_KEY, CACHE_EXPIRE, json.dumps(response))
                except Exception as re:
                    print(f"Shinhan Redis save failed: {re}")
            return response
        
        return {"last_updated": None, "data": []}
    except Exception: return {"last_updated": None, "data": []}

@app.get("/api/kb-cards")
async def get_kb_cards():
    try:
        import json
        if r:
            cached = r.get(KB_CACHE_KEY)
            if cached: return json.loads(cached)

        local_path = "kb_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            response = {"last_updated": last_updated, "data": data}
            if r:
                try:
                    r.setex(KB_CACHE_KEY, CACHE_EXPIRE, json.dumps(response))
                except Exception as re:
                    print(f"KB Redis save failed: {re}")
            return response
        
        return {"last_updated": None, "data": []}
    except Exception: return {"last_updated": None, "data": []}

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
        print(f"[{datetime.now()}] Starting Hana background crawl...")
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
                        
                    for ev in event_list:
                        # 필드 매핑
                        title = ev.get("EVN_TIT_NM", "")
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
                with open("hana_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"Hana file save failed: {fe}")

            if r:
                try:
                    r.setex(HANA_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                     print(f"Hana Redis save failed: {re}")
            
            print(f"[{datetime.now()}] Hana crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] Hana crawl failed: {e}")

@app.get("/api/hana-cards")
async def get_hana_cards():
    try:
        import json
        if r:
            cached = r.get(HANA_CACHE_KEY)
            if cached: return json.loads(cached)

        local_path = "hana_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            response = {"last_updated": last_updated, "data": data}
            if r:
                try:
                    r.setex(HANA_CACHE_KEY, CACHE_EXPIRE, json.dumps(response))
                except Exception: pass
            return response
        
        return {"last_updated": None, "data": []}
    except Exception: return {"last_updated": None, "data": []}

@app.post("/api/hana/update")
async def update_hana(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_hana_bg)
    return {"status": "started"}

# 우리카드 데이터 갱신 (백그라운드)
async def crawl_woori_bg():
    try:
        print(f"[{datetime.now()}] Starting Woori background crawl...")
        all_events = []
        base_url = "https://m.wooricard.com"
        api_url = f"{base_url}/dcmw/yh1/bnf/bnf02/prgevnt/getPrgEvntList.pwkjson"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                "Content-Type": "application/json"
            }
            
            # 페이지별로 데이터 수집
            for page_idx in range(1, 20):  # 최대 20페이지
                payload = {
                    "bnf02PrgEvntVo": {
                        "evntCtgrNo": "",
                        "searchKwrd": "",
                        "sortOrd": "orderNew",
                        "pageIndex": str(page_idx),
                        "pageSize": "20",
                        "evntItgCfcd": ""
                    }
                }
                
                try:
                    response = await client.post(api_url, json=payload, headers=headers)
                    if response.status_code != 200:
                        break
                        
                    res_json = response.json()
                    event_list = res_json.get("prgEvntList", [])
                    
                    if not event_list:
                        break
                        
                    for ev in event_list:
                        title = ev.get("cardEvntNm", "") or ev.get("mblDocTitlTxt", "")
                        start_date = ev.get("evntSdt", "")
                        end_date = ev.get("evntEdt", "")
                        
                        # 날짜 포맷팅 (YYYYMMDD -> YYYY.MM.DD)
                        if len(start_date) == 8:
                            start_date = f"{start_date[:4]}.{start_date[4:6]}.{start_date[6:]}"
                        if len(end_date) == 8:
                            end_date = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:]}"
                        
                        img_path = ev.get("fileCoursWeb", "")
                        if img_path and not img_path.startswith("http"):
                            img_path = f"{base_url}{img_path}"
                            
                        # 우리카드는 sessionStorage 사용으로 직접 링크 어려움
                        # 목록 페이지로 링크
                        link = f"{base_url}/dcmw/yh1/bnf/bnf02/prgevnt/M1BNF202S00.do"
                        
                        all_events.append({
                            "category": "우리카드",
                            "eventName": title,
                            "period": f"{start_date} ~ {end_date}",
                            "link": link,
                            "image": img_path,
                            "bgColor": "#ffffff"
                        })
                        
                except Exception as e:
                    print(f"Error parsing Woori page {page_idx}: {e}")
                    break

        if all_events:
            try:
                with open("woori_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"Woori file save failed: {fe}")

            if r:
                try:
                    r.setex(WOORI_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                     print(f"Woori Redis save failed: {re}")
            
            print(f"[{datetime.now()}] Woori crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] Woori crawl failed: {e}")

@app.get("/api/woori-cards")
async def get_woori_cards():
    try:
        import json
        if r:
            cached = r.get(WOORI_CACHE_KEY)
            if cached: return json.loads(cached)

        local_path = "woori_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            response = {"last_updated": last_updated, "data": data}
            if r:
                try:
                    r.setex(WOORI_CACHE_KEY, CACHE_EXPIRE, json.dumps(response))
                except Exception: pass
            return response
        return {"last_updated": None, "data": []}
    except Exception: return {"last_updated": None, "data": []}

@app.post("/api/woori/update")
async def update_woori(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_woori_bg)
    return {"status": "started"}

# BC카드 데이터 갱신 (백그라운드)
async def crawl_bc_bg():
    try:
        print(f"[{datetime.now()}] Starting BC background crawl...")
        all_events = []
        base_url = "https://web.paybooc.co.kr"
        target_url = f"{base_url}/web/evnt/main"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = await client.get(target_url, headers=headers)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "lxml")
                
                # BC카드 이벤트 아이템 선택자
                items = soup.select(".event-list .event-item, .evnt-list .item, article.event")
                
                for item in items:
                    try:
                        title_elem = item.select_one(".title, .event-title, h3, h4")
                        title = title_elem.text.strip() if title_elem else ""
                        
                        img_elem = item.select_one("img")
                        img_src = img_elem.get("src", "") if img_elem else ""
                        if img_src and not img_src.startswith("http"):
                            img_src = f"{base_url}{img_src}"
                        
                        link_elem = item.select_one("a")
                        link = link_elem.get("href", "") if link_elem else ""
                        if link and not link.startswith("http"):
                            link = f"{base_url}{link}"
                        
                        period_elem = item.select_one(".period, .date, .event-period")
                        period = period_elem.text.strip() if period_elem else ""
                        
                        if title:
                            all_events.append({
                                "category": "BC카드",
                                "eventName": title,
                                "period": period,
                                "link": link or target_url,
                                "image": img_src,
                                "bgColor": "#ffffff"
                            })
                    except Exception:
                        continue

        if all_events:
            try:
                with open("bc_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"BC file save failed: {fe}")

            if r:
                try:
                    r.setex(BC_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                     print(f"BC Redis save failed: {re}")
            
            print(f"[{datetime.now()}] BC crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] BC crawl failed: {e}")

@app.get("/api/bc-cards")
async def get_bc_cards():
    try:
        import json
        if r:
            cached = r.get(BC_CACHE_KEY)
            if cached: return json.loads(cached)

        local_path = "bc_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            response = {"last_updated": last_updated, "data": data}
            if r:
                try:
                    r.setex(BC_CACHE_KEY, CACHE_EXPIRE, json.dumps(response))
                except Exception: pass
            return response
        return {"last_updated": None, "data": []}
    except Exception: return {"last_updated": None, "data": []}

@app.post("/api/bc/update")
async def update_bc(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_bc_bg)
    return {"status": "started"}

# 삼성카드 데이터 갱신 (백그라운드)
async def crawl_samsung_bg():
    try:
        print(f"[{datetime.now()}] Starting Samsung background crawl...")
        all_events = []
        base_url = "https://www.samsungcard.com"
        target_url = f"{base_url}/personal/event/ing/UHPPBE1401M0.jsp"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = await client.get(target_url, headers=headers)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "lxml")
                
                # 삼성카드 이벤트 아이템 선택자
                items = soup.select(".event-list li, .list-event .item, .evt-list .evt-item")
                
                for item in items:
                    try:
                        title_elem = item.select_one(".title, .evt-title, strong, .tit")
                        title = title_elem.text.strip() if title_elem else ""
                        
                        img_elem = item.select_one("img")
                        img_src = img_elem.get("src", "") if img_elem else ""
                        if img_src and not img_src.startswith("http"):
                            if img_src.startswith("//"):
                                img_src = f"https:{img_src}"
                            else:
                                img_src = f"{base_url}{img_src}"
                        
                        link_elem = item.select_one("a")
                        link = link_elem.get("href", "") if link_elem else ""
                        if link and not link.startswith("http"):
                            link = f"{base_url}{link}"
                        
                        period_elem = item.select_one(".period, .date, .evt-period")
                        period = period_elem.text.strip() if period_elem else ""
                        
                        if title:
                            all_events.append({
                                "category": "삼성카드",
                                "eventName": title,
                                "period": period,
                                "link": link or target_url,
                                "image": img_src,
                                "bgColor": "#ffffff"
                            })
                    except Exception:
                        continue

        if all_events:
            try:
                with open("samsung_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"Samsung file save failed: {fe}")

            if r:
                try:
                    r.setex(SAMSUNG_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                     print(f"Samsung Redis save failed: {re}")
            
            print(f"[{datetime.now()}] Samsung crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] Samsung crawl failed: {e}")

@app.get("/api/samsung-cards")
async def get_samsung_cards():
    try:
        import json
        if r:
            cached = r.get(SAMSUNG_CACHE_KEY)
            if cached: return json.loads(cached)

        local_path = "samsung_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            response = {"last_updated": last_updated, "data": data}
            if r:
                try:
                    r.setex(SAMSUNG_CACHE_KEY, CACHE_EXPIRE, json.dumps(response))
                except Exception: pass
            return response
        return {"last_updated": None, "data": []}
    except Exception: return {"last_updated": None, "data": []}

@app.post("/api/samsung/update")
async def update_samsung(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(crawl_samsung_bg)
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
    3. 둘 다 없으면 실시간 크롤링 (시간 소요됨)
    """
    try:
        import json
        cached_data = r.get(CACHE_KEY)
        if cached_data:
            return json.loads(cached_data)
            
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
            
            r.setex(CACHE_KEY, CACHE_EXPIRE, json.dumps(response_data))
            return response_data

        # 3. 로컬 파일도 없으면 빈 값 반환 (실시간 크롤링 방지)
        if not os.path.exists(local_path):
             return {"last_updated": None, "message": "데이터가 없습니다.", "data": []}
        
        return {"last_updated": None, "data": []}

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
        print(f"[{datetime.now()}] Starting KFCC background crawl...")
        from kfcc_crawler import run_crawler
        # json은 상단 import 사용
        
        data = await run_crawler()
        
        # 파일 저장
        try:
            with open("kfcc_data.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as fe:
            print(f"KFCC file save failed: {fe}")
            
        # 캐시 갱신
        if r:
            try:
                r.setex(CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": data}))
            except Exception as re:
                print(f"KFCC Redis save failed: {re}")
        else:
            print("Redis not available, skipped cache update.")
                
        print(f"[{datetime.now()}] KFCC background crawl finished. {len(data)-1} records updated.")
    except Exception as e:
        print(f"[{datetime.now()}] KFCC background crawl failed: {e}")

# 스케줄러 설정
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

scheduler = AsyncIOScheduler()

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
async def root():
    html_content = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Oracle Crawler</title>
    <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-color: #ffffff; --text-color: #1d1d1f; }
        body { font-family: 'Pretendard', -apple-system, sans-serif; background: var(--bg-color); color: var(--text-color); margin: 0; padding: 0; }
        .container { max-width: 980px; margin: 0 auto; padding: 100px 20px; text-align: center; }
        h1 { font-size: 56px; font-weight: 700; letter-spacing: -0.005em; margin: 0 0 20px; }
        .time-display { font-size: 24px; color: #86868b; margin-bottom: 60px; font-weight: 400; }
        .nav-card { background: #fbfbfd; border-radius: 24px; padding: 50px; text-decoration: none; color: inherit; transition: all 0.3s cubic-bezier(0.25,0.1,0.25,1); display: inline-flex; flex-direction: column; align-items: center; width: 300px; box-shadow: 0 4px 20px rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.05); }
        .nav-card:hover { transform: scale(1.02); box-shadow: 0 20px 40px rgba(0,0,0,0.08); background: #fff; }
        .icon { font-size: 48px; margin-bottom: 16px; }
        .nav-title { font-size: 22px; font-weight: 600; margin-bottom: 8px; }
        .nav-desc { color: #86868b; font-size: 16px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Oracle Crawler</h1>
        <div id="clock" class="time-display">Loading...</div>
        <a href="/card-events" class="nav-card">
            <span class="icon">💳</span>
            <span class="nav-title">카드사 이벤트</span>
            <span class="nav-desc">전체 카드사의 최신 혜택 모음</span>
        </a>
    </div>
    <script>
        function updateTime() {
            const now = new Date();
            const options = { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long', hour: '2-digit', minute: '2-digit', second: '2-digit' };
            document.getElementById('clock').innerText = now.toLocaleDateString('ko-KR', options);
        }
        setInterval(updateTime, 1000);
        updateTime();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


