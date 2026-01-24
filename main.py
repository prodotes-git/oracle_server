import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import os
import redis
import psutil
import time
from datetime import datetime

app = FastAPI()

# Redis 연결 설정
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

# 서버 시작 시간 기록 (Uptime 계산용)
boot_time = time.time()

# 데이터 캐싱을 위한 설정
DATA_URL = "https://raw.githubusercontent.com/if1live/shiroko-kfcc/interest-rate/summary/report_mat.json"
CACHE_KEY = "kfcc_data_cache"
KB_CACHE_KEY = "kb_card_events_cache_v3" # 이미지 정보를 포함한 v3
SHINHAN_CACHE_KEY = "shinhan_card_events_cache_v1"
SHINHAN_MYSHOP_CACHE_KEY = "shinhan_myshop_cache_v2" # 경로 수정 반영을 위한 v2
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
            "Referer": "https://www.shinhancard.com/mob/MOBFM501N/MOBFM501R31.shc",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        }
        payload = {"QY_CCD": "T"}
        
        all_coupons = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(api_url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # GRID1에 쿠폰 정보들이 담겨 있음
                grid = data.get("mbw_message", {}).get("GRID1", {})
                
                # 병렬 리스트 형식이므로 인덱스로 순회
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
                    
                    # 이미지 경로 처리
                    if img and not img.startswith('http'):
                        img = f"{base_url}{img}"

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

        if all_coupons:
            r.setex(SHINHAN_MYSHOP_CACHE_KEY, CACHE_EXPIRE, json.dumps(all_coupons))
        return all_coupons
    except Exception as e:
        print(f"Shinhan MyShop API Error: {e}")
        return []

@app.get("/api/shinhan-cards")
async def get_shinhan_cards():
    """
    신한카드 이벤트 데이터를 가져와서 정제하여 반환합니다.
    """
    try:
        import json
        # 1. 캐시 확인
        try:
            cached = r.get(SHINHAN_CACHE_KEY)
            if cached:
                data = json.loads(cached)
                if data: return data
        except Exception: pass

        all_events = []
        base_url = "https://www.shinhancard.com"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 신한카드는 01, 02... 형식의 JSON 파일을 사용
            for i in range(1, 5):
                api_url = f"{base_url}/logic/json/evnPgsList0{i}.json"
                headers = {
                    "Referer": "https://www.shinhancard.com/",
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
                }
                
                response = await client.get(api_url, headers=headers)
                if response.status_code != 200:
                    break
                
                data = response.json()
                events = data.get("root", {}).get("evnlist", [])
                if not events:
                    break
                
                for ev in events:
                    # 기간 포맷팅 (YYYYMMDD -> YYYY.MM.DD)
                    start = ev.get('mobWbEvtStd', '')
                    end = ev.get('mobWbEvtEdd', '')
                    if len(start) == 8: start = f"{start[:4]}.{start[4:6]}.{start[6:]}"
                    if len(end) == 8: end = f"{end[:4]}.{end[4:6]}.{end[6:]}"
                    
                    # 이미지 및 링크 처리
                    img_url = ev.get('hpgEvtCtgImgUrlAr', '')
                    if img_url and not img_url.startswith('http'):
                        img_url = f"{base_url}{img_url}"
                    
                    link_url = ev.get('hpgEvtDlPgeUrlAr', '')
                    if link_url and not link_url.startswith('http'):
                        link_url = f"{base_url}{link_url}"

                    all_events.append({
                        "category": ev.get('hpgEvtSmrTt', '이벤트'),
                        "eventName": f"{ev.get('evtImgSlTilNm', '')} {ev.get('mobWbEvtNm', '')}".strip(),
                        "period": f"{start} ~ {end}" if start and end else "상시 진행",
                        "link": link_url,
                        "image": img_url,
                        "bgColor": "#ffffff" # 신한카드는 주로 화이트 배경
                    })
        
        # 2. 결과가 있을 때만 캐싱
        if all_events:
            try:
                r.setex(SHINHAN_CACHE_KEY, CACHE_EXPIRE, json.dumps(all_events))
            except Exception: pass
                
        return all_events
        
    except Exception as e:
        print(f"Shinhan Card API Error: {e}")
        return []

@app.get("/api/kb-cards")
async def get_kb_cards():
    """
    KB국민카드 이벤트 데이터를 가져와서 정제하여 반환합니다.
    """
    try:
        import json
        # 1. 캐시 확인
        try:
            cached = r.get(KB_CACHE_KEY)
            if cached:
                data = json.loads(cached)
                if data: # 비어있지 않은 경우만 반환
                    return data
        except Exception as re:
            print(f"Redis Cache Error: {re}")

        all_events = []
        api_url = "https://m.kbcard.com/BON/API/MBBACXHIABNC0064"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            for page in range(1, 15):
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
                
                response = await client.post(api_url, data=payload, headers=headers)
                if response.status_code != 200:
                    print(f"KB API HTTP Error: {response.status_code}")
                    break
                
                res_json = response.json()
                events = res_json.get("evntList", [])
                if not events:
                    break
                
                for ev in events:
                    category_code = ev.get("evntBonContents", "")
                    category_map = {"01": "포인트/캐시백", "02": "할인/무이자", "03": "경품", "04": "기타"}
                    category = category_map.get(category_code, "이벤트")
                    
                    # 이미지 경로 처리
                    img_path = ev.get('evtImgPath', '')
                    if img_path and not img_path.startswith('http'):
                        img_path = f"https://img1.kbcard.com/ST/img/cxc{img_path}"

                    all_events.append({
                        "category": category,
                        "eventName": f"{ev.get('evtNm', '')} {ev.get('evtSubNm', '')}".strip(),
                        "period": ev.get("evtYMD", ""),
                        "link": f"https://m.kbcard.com/BON/DVIEW/MBBMCXHIABNC0026?evntSerno={ev.get('evtNo')}&evntMain=Y",
                        "image": img_path,
                        "bgColor": ev.get('bckgColrCtt', '#f2f2f7')
                    })
                
                if page >= res_json.get("totalPageCount", 0):
                    break
        
        # 2. 결과가 있을 때만 캐싱
        if all_events:
            try:
                r.setex(KB_CACHE_KEY, CACHE_EXPIRE, json.dumps(all_events))
            except Exception as se:
                print(f"Redis Save Error: {se}")
                
        return all_events
        
    except Exception as e:
        print(f"KB Card API General Error: {e}")
        return []

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
    내 서버에서 독립적으로 데이터를 제공하는 API입니다.
    Redis를 사용하여 데이터를 캐싱하되, Redis 오류 시 원본에서 직접 가져옵니다.
    """
    cached_data = None
    try:
        # 1. 캐시에 데이터가 있는지 확인 (실패 시 조용히 넘어감)
        cached_data = r.get(CACHE_KEY)
    except Exception as e:
        print(f"Redis 오류 (무시됨): {e}")

    if cached_data:
        try:
            import json
            return json.loads(cached_data)
        except Exception:
            pass

    # 2. 캐시가 없거나 Redis 오류 시 원본에서 가져옴
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(DATA_URL, timeout=10.0)
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="데이터 원본을 가져올 수 없습니다.")
            
            data = response.json()
            
            # 3. 가져온 데이터를 캐싱 시도 (실패해도 응답은 전달)
            try:
                r.setex(CACHE_KEY, CACHE_EXPIRE, response.text)
            except Exception as e:
                print(f"Redis 캐싱 실패 (무시됨): {e}")
                
            return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")

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
                    <div class="icon-wrapper" style="background: #f2f2f7; color: #1d1d1f;">🚀</div>
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

@app.get("/kfcc", response_class=HTMLResponse)
def kfcc_rates():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>금리조회 | Saemaul Geumgo</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f;
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
            .main-content { max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 1.5rem; }

            .product-tabs { display: flex; background: #E8E8ED; padding: 4px; border-radius: 12px; margin-bottom: 2rem; }
            .tab-btn {
                flex: 1; border: none; padding: 10px; border-radius: 10px; font-family: inherit;
                font-weight: 600; cursor: pointer; background: none; color: var(--text-secondary); transition: all 0.2s;
            }
            .tab-btn.active { background: white; color: var(--accent-color); box-shadow: 0 2px 4px rgba(0,0,0,0.1); }

            .filter-section { margin-bottom: 1.5rem; display: flex; gap: 10px; }
            .search-input { flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color); font-size: 1rem; outline: none; }
            .region-select { padding: 12px; border-radius: 12px; border: 1px solid var(--border-color); background: white; outline: none; }

            .top-rank-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
            .rank-card { background: linear-gradient(135deg, #0071e3 0%, #00c6fb 100%); color: white; padding: 1.5rem; border-radius: 20px; box-shadow: 0 10px 20px rgba(0,113,227,0.2); }
            .rank-title { font-size: 0.8rem; font-weight: 600; opacity: 0.8; }
            .rank-name { font-size: 1.2rem; font-weight: 700; margin: 0.5rem 0; }
            .rank-rate { font-size: 2rem; font-weight: 700; }

            .rate-list { display: grid; gap: 12px; }
            .rate-item {
                background: white; padding: 1.5rem; border-radius: 20px; display: flex; justify-content: space-between;
                align-items: center; box-shadow: 0 2px 8px rgba(0,0,0,0.02);
            }

            .branch-info h3 { font-size: 1.1rem; margin-bottom: 4px; }
            .branch-info p { font-size: 0.85rem; color: var(--text-secondary); }
            .rate-value { font-family: 'Outfit', sans-serif; font-size: 1.5rem; font-weight: 700; color: var(--blue-color); }
            .loading { text-align: center; padding: 3rem; color: var(--text-secondary); }
        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/" class="back-btn">← 대시보드</a>
                <div style="font-weight: 600;">새마을금고 금리조회</div>
                <div style="width: 60px;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>전국 금리 실시간 비교</h1>
            <div class="product-tabs">
                <button class="tab-btn active" onclick="switchProduct(3)">정기예금</button>
                <button class="tab-btn" onclick="switchProduct(4)">정기적금</button>
                <button class="tab-btn" onclick="switchProduct(5)">자유적금</button>
            </div>
            <div class="top-rank-container" id="topRank"></div>
            <div class="filter-section">
                <select class="region-select" id="regionFilter" onchange="filterData()">
                    <option value="">전체 지역</option>
                    <option value="서울">서울</option>
                    <option value="경기">경기</option>
                    <option value="인천">인천</option>
                    <option value="부산">부산</option>
                    <option value="대구">대구</option>
                    <option value="광주">광주</option>
                    <option value="대전">대전</option>
                    <option value="울산">울산</option>
                    <option value="세종">세종</option>
                    <option value="강원">강원</option>
                    <option value="충북">충북</option>
                    <option value="충남">충남</option>
                    <option value="전북">전북</option>
                    <option value="전남">전남</option>
                    <option value="경북">경북</option>
                    <option value="경남">경남</option>
                    <option value="제주">제주</option>
                </select>
                <input type="text" class="search-input" id="searchInput" placeholder="금고 이름으로 검색..." onkeyup="filterData()">
            </div>
            <div id="rateList" class="rate-list">
                <div class="loading">데이터를 불러오는 중입니다...</div>
            </div>
        </div>

        <script>
            let allData = [];
            let currentProductIdx = 3; 

            async function fetchData() {
                try {
                    // 외부 사이트가 아닌 내 서버의 API(/api/kfcc)에서 데이터를 가져옵니다.
                    const response = await fetch('/api/kfcc');
                    const data = await response.json();
                    allData = data.slice(1);
                    renderData();
                } catch (error) {
                    document.getElementById('rateList').innerHTML = '<div class="loading">내 서버의 API에서 데이터를 불러오지 못했습니다.</div>';
                }
            }

            function switchProduct(idx) {
                currentProductIdx = idx;
                document.querySelectorAll('.tab-btn').forEach((btn, i) => {
                    btn.classList.toggle('active', i === (idx - 3));
                });
                renderData();
            }

            function filterData() { renderData(); }

            function renderData() {
                const region = document.getElementById('regionFilter').value;
                const search = document.getElementById('searchInput').value.toLowerCase();
                
                let filtered = allData.filter(item => {
                    const matchesRegion = region === "" || item[2].includes(region);
                    const matchesSearch = search === "" || item[1].toLowerCase().includes(search);
                    return matchesRegion && matchesSearch && item[currentProductIdx] !== null;
                });

                filtered.sort((a, b) => b[currentProductIdx] - a[currentProductIdx]);

                const top3 = filtered.slice(0, 3);
                document.getElementById('topRank').innerHTML = top3.map((item, i) => `
                    <div class="rank-card">
                        <div class="rank-title">${i+1}위 고금리</div>
                        <div class="rank-name">${item[1]}</div>
                        <div class="rank-rate">${item[currentProductIdx]}%</div>
                        <div style="font-size: 0.7rem; opacity: 0.7;">${item[2]}</div>
                    </div>
                `).join('');

                const listHtml = filtered.map(item => `
                    <div class="rate-item">
                        <div class="branch-info">
                            <h3>${item[1]} 새마을금고</h3>
                            <p>${item[2]}</p>
                            <p style="font-size: 0.7rem; margin-top: 4px;">기준일: ${item[6]}</p>
                        </div>
                        <div class="rate-value">${item[currentProductIdx]}%</div>
                    </div>
                `).join('');
                document.getElementById('rateList').innerHTML = listHtml || '<div class="loading">검색 결과가 없습니다.</div>';
            }
            fetchData();
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
                --accent-color: #1d1d1f;
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
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 1.5rem;
            }

            .card-link {
                background: white;
                border: 1px solid var(--border-color);
                border-radius: 24px;
                padding: 2rem 1.5rem;
                text-decoration: none;
                color: inherit;
                transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
                display: flex;
                flex-direction: column;
                align-items: center;
                box-shadow: 0 4px 12px rgba(0,0,0,0.03);
            }

            .card-link:hover {
                transform: translateY(-8px);
                box-shadow: 0 20px 40px rgba(0,0,0,0.08);
                border-color: var(--blue-color);
            }

            .card-logo {
                width: 64px;
                height: 64px;
                border-radius: 16px;
                margin-bottom: 1.2rem;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.8rem;
                background: #f2f2f7;
            }

            .card-name { font-weight: 600; font-size: 1.1rem; margin-bottom: 0.4rem; }
            .card-desc { font-size: 0.85rem; color: var(--text-secondary); }

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
                <input type="text" id="cardSearch" placeholder="카드사 이름을 검색해보세요..." onkeyup="filterCards()">
            </div>

            <div class="card-grid" id="cardGrid">
                <a href="/card-events/shinhan" class="card-link" data-name="신한카드">
                    <div class="card-logo" style="background: #0046ff; color: white;">S</div>
                    <div class="card-name">신한카드</div>
                    <div class="card-desc">이벤트 전체 검색하기</div>
                </a>
                <a href="https://www.samsungcard.com/personal/event/ing/list" target="_blank" class="card-link" data-name="삼성카드">
                    <div class="card-logo" style="background: #0056b3; color: white;">S</div>
                    <div class="card-name">삼성카드</div>
                    <div class="card-desc">진행중인 이벤트 보기</div>
                </a>
                <a href="https://m.hyundaicard.com/mp/ev/MPEV0101_01.hc" target="_blank" class="card-link" data-name="현대카드">
                    <div class="card-logo" style="background: #000; color: white;">H</div>
                    <div class="card-name">현대카드</div>
                    <div class="card-desc">진행중인 이벤트 보기</div>
                </a>
                <a href="/card-events/kb" class="card-link" data-name="KB국민카드">
                    <div class="card-logo" style="background: #ffbc00; color: #1d1d1f;">K</div>
                    <div class="card-name">KB국민카드</div>
                    <div class="card-desc">이벤트 전체 검색하기</div>
                </a>
                <a href="https://www.lottecard.co.kr/app/LPBNNEA_V100.lc" target="_blank" class="card-link" data-name="롯데카드">
                    <div class="card-logo" style="background: #ed1c24; color: white;">L</div>
                    <div class="card-name">롯데카드</div>
                    <div class="card-desc">진행중인 이벤트 보기</div>
                </a>
                <a href="https://www.wooricard.com/wccd/CHC/CHCM0101_01.hc" target="_blank" class="card-link" data-name="우리카드">
                    <div class="card-logo" style="background: #007bc3; color: white;">W</div>
                    <div class="card-name">우리카드</div>
                    <div class="card-desc">진행중인 이벤트 보기</div>
                </a>
                <a href="https://www.hanacard.co.kr/OPN00000000N.web?schID=pcd&mID=OPN00000000N" target="_blank" class="card-link" data-name="하나카드">
                    <div class="card-logo" style="background: #008485; color: white;">H</div>
                    <div class="card-name">하나카드</div>
                    <div class="card-desc">진행중인 이벤트 보기</div>
                </a>
                <a href="https://m.bccard.com/app/mobileweb/EvntList.do" target="_blank" class="card-link" data-name="BC카드">
                    <div class="card-logo" style="background: #ed1c24; color: white;">B</div>
                    <div class="card-name">BC카드</div>
                    <div class="card-desc">진행중인 이벤트 보기</div>
                </a>
            </div>
        </div>

        <script>
            function filterCards() {
                const search = document.getElementById('cardSearch').value.toLowerCase();
                const cards = document.querySelectorAll('.card-link');
                
                cards.forEach(card => {
                    const name = card.getAttribute('data-name').toLowerCase();
                    if (name.includes(search)) {
                        card.style.display = 'flex';
                    } else {
                        card.style.display = 'none';
                    }
                });
            }
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
                --accent-color: #1d1d1f;
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

            .nav-content { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            
            .main-content { max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 1.5rem; }

            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }

            .search-input {
                flex: 1; padding: 16px 20px; border-radius: 16px; border: 1px solid var(--border-color);
                box-shadow: 0 4px 6px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 1rem;
            }
            .search-input:focus { border-color: var(--kb-color); box-shadow: 0 4px 12px rgba(255,188,0,0.15); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); 
                gap: 1.5rem; 
            }
            .event-card {
                background: white; border-radius: 24px; overflow: hidden; display: flex; flex-direction: column;
                border: 1px solid var(--border-color); text-decoration: none; color: inherit; transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
                height: 100%;
            }
            .event-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.08); }

            .thumb-area {
                width: 100%;
                aspect-ratio: 16/9;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                overflow: hidden;
            }
            .thumb-img {
                width: 80%;
                height: 80%;
                object-fit: contain;
                z-index: 2;
            }
            .card-body { padding: 1.5rem; flex: 1; display: flex; flex-direction: column; }
            .category-tag {
                background: #f2f2f7; color: var(--text-secondary); padding: 4px 10px; border-radius: 8px; font-size: 0.7rem; font-weight: 700;
                align-self: flex-start; margin-bottom: 0.8rem;
            }
            .event-title { font-size: 1rem; font-weight: 700; line-height: 1.4; margin-bottom: 0.8rem; flex: 1; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
            .event-period { font-size: 0.75rem; color: var(--text-secondary); }

            .loading { text-align: center; padding: 4rem; grid-column: 1 / -1; color: var(--text-secondary); }
            .stats { font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 1rem; }
        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600;">KB국민카드 이벤트</div>
                <div style="width: 80px;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>이벤트 전체 검색</h1>
            
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

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/kb-cards');
                    allEvents = await response.json();
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const filtered = allEvents.filter(ev => 
                    ev.eventName.toLowerCase().includes(search) || 
                    ev.category.toLowerCase().includes(search)
                );
                renderEvents(filtered);
            }

            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 이벤트 검색됨`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">검색 결과가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card">
                        <div class="thumb-area" style="background-color: ${ev.bgColor}">
                            <img src="${ev.image}" class="thumb-img" onerror="this.style.display='none'">
                        </div>
                        <div class="card-body">
                            <span class="category-tag">${ev.category}</span>
                            <div class="event-title">${ev.eventName}</div>
                            <div class="event-period">${ev.period}</div>
                        </div>
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
                --accent-color: #1d1d1f;
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

            .nav-content { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            
            .main-content { max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 0.5rem; }
            .official-link { display: inline-block; margin-bottom: 1.5rem; color: var(--sh-color); text-decoration: none; font-size: 0.9rem; font-weight: 500; }
            .official-link:hover { text-decoration: underline; }

            .search-section {
                display: flex; gap: 1rem; margin-bottom: 2rem;
            }

            .search-input {
                flex: 1; padding: 16px 20px; border-radius: 16px; border: 1px solid var(--border-color);
                box-shadow: 0 4px 6px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 1rem;
            }
            .search-input:focus { border-color: var(--sh-color); box-shadow: 0 4px 12px rgba(0,70,255,0.15); }

            .event-list { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); 
                gap: 1.5rem; 
            }
            .event-card {
                background: white; border-radius: 24px; overflow: hidden; display: flex; flex-direction: column;
                border: 1px solid var(--border-color); text-decoration: none; color: inherit; transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
                height: 100%;
            }
            .event-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.08); }

            .thumb-area {
                width: 100%;
                aspect-ratio: 16/9;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                overflow: hidden;
            }
            .thumb-img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                transition: transform 0.5s ease;
            }
            .event-card:hover .thumb-img { transform: scale(1.05); }

            .card-body { padding: 1.5rem; flex: 1; display: flex; flex-direction: column; }
            .category-tag {
                background: #f2f2f7; color: var(--text-secondary); padding: 4px 10px; border-radius: 8px; font-size: 0.7rem; font-weight: 700;
                align-self: flex-start; margin-bottom: 0.8rem;
            }
            .event-title { font-size: 1rem; font-weight: 700; line-height: 1.4; margin-bottom: 0.8rem; flex: 1; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
            .event-period { font-size: 0.75rem; color: var(--text-secondary); }

            .loading { text-align: center; padding: 4rem; grid-column: 1 / -1; color: var(--text-secondary); }
            .stats { font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 1rem; }
        </style>
    </head>
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600;">신한카드 이벤트</div>
                <div style="width: 80px;"></div>
            </div>
        </div>

        <div class="main-content">
            <h1>이벤트 전체 검색</h1>
            <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
                <a href="https://www.shinhancard.com/mob/MOBFM829N/MOBFM829R03.shc?sourcePage=R01" target="_blank" class="official-link">공식 이벤트 목록 ↗</a>
                <a href="https://www.shinhancard.com/mob/MOBFM501N/MOBFM501R31.shc" target="_blank" class="official-link" style="color: #e91e63;">공식 마이샵 쿠폰 ↗</a>
            </div>
            
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

            async function fetchEvents() {
                try {
                    const [eventsRes, myshopRes] = await Promise.all([
                        fetch('/api/shinhan-cards'),
                        fetch('/api/shinhan-myshop')
                    ]);
                    
                    const events = await eventsRes.json();
                    const myshop = await myshopRes.json();
                    
                    allEvents = [...events, ...myshop];
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const filtered = allEvents.filter(ev => 
                    ev.eventName.toLowerCase().includes(search) || 
                    ev.category.toLowerCase().includes(search)
                );
                renderEvents(filtered);
            }

            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                
                stats.innerText = `총 ${events.length}개의 혜택 검색됨`;
                
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">검색 결과가 없습니다.</div>';
                    return;
                }

                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card">
                        <div class="thumb-area">
                            <img src="${ev.image}" class="thumb-img" style="object-fit: contain; width: 85%; height: 85%;" onerror="this.src='https://www.shinhancard.com/pconts/images/dx/common/no_image.png'">
                        </div>
                        <div class="card-body">
                            <span class="category-tag" style="${ev.category === '마이샵 쿠폰' ? 'background: #ffe1ed; color: #e91e63;' : ''}">${ev.category}</span>
                            <div class="event-title">${ev.eventName}</div>
                            <div class="event-period">${ev.period}</div>
                        </div>
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
