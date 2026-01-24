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
CACHE_EXPIRE = 3600  # 1시간 동안 캐시 유지

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
        <title>Oracle Dashboard | Premium</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-color: #F5F5F7;
                --card-bg: rgba(255, 255, 255, 0.7);
                --accent-color: #1d1d1f;
                --text-secondary: #6e6e73;
                --glass-border: rgba(255, 255, 255, 0.5);
                --success-color: #28cd41;
                --blue-color: #0071e3;
            }}
            
            * {{ margin: 0; padding: 0; box-sizing: border-box; -webkit-font-smoothing: antialiased; }}
            
            body {{
                background-color: var(--bg-color);
                color: var(--accent-color);
                font-family: 'Inter', sans-serif;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                background: linear-gradient(180deg, #FFFFFF 0%, #F5F5F7 100%);
                padding: 2rem;
            }}

            .container {{ width: 100%; max-width: 600px; animation: fadeIn 1.2s cubic-bezier(0.2, 0.8, 0.2, 1); }}

            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(15px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}

            .main-card {{
                background: var(--card-bg);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border);
                border-radius: 40px;
                padding: 3.5rem 3rem;
                text-align: center;
                margin-bottom: 1.5rem;
                box-shadow: 0 30px 60px rgba(0,0,0,0.06);
            }}

            h1 {{
                font-family: 'Outfit', sans-serif;
                font-size: 3rem;
                font-weight: 600;
                letter-spacing: -0.04em;
                margin-bottom: 2.5rem;
                color: var(--accent-color);
            }}

            .grid-stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.2rem; margin-top: 1rem; }}

            .stat-box {{
                background: rgba(0, 0, 0, 0.02);
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 24px;
                padding: 1.8rem 1rem;
                transition: all 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
            }}

            .stat-box:hover {{
                transform: scale(1.02);
                background: rgba(255, 255, 255, 0.9);
                box-shadow: 0 10px 30px rgba(0,0,0,0.04);
            }}

            .stat-label {{
                font-size: 0.75rem;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.12em;
                margin-bottom: 0.8rem;
                font-weight: 600;
            }}

            .stat-value {{ font-family: 'Outfit', sans-serif; font-size: 1.6rem; font-weight: 600; color: var(--accent-color); }}

            .menu-section {{ margin-top: 3rem; display: grid; gap: 1rem; }}

            .menu-button {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                background: white;
                border: 1px solid rgba(0,0,0,0.05);
                padding: 1.5rem 2rem;
                border-radius: 24px;
                text-decoration: none;
                color: var(--accent-color);
                transition: all 0.3s ease;
                box-shadow: 0 4px 12px rgba(0,0,0,0.02);
            }}

            .menu-button:hover {{ transform: scale(1.02); box-shadow: 0 12px 24px rgba(0,0,0,0.06); }}

            .menu-button .icon {{
                width: 44px; height: 44px; background: var(--blue-color); color: white; border-radius: 12px;
                display: flex; align-items: center; justify-content: center; font-size: 1.2rem;
            }}

            .menu-button .text {{ flex: 1; margin-left: 1.2rem; text-align: left; }}
            .menu-button .title {{ font-weight: 600; font-size: 1.1rem; }}
            .menu-button .subtitle {{ font-size: 0.8rem; color: var(--text-secondary); }}

            .visits-section {{ margin-top: 3.5rem; border-top: 1px solid rgba(0, 0, 0, 0.05); padding-top: 2.5rem; }}
            .visits-label {{ font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 0.8rem; font-weight: 400; }}
            .visits-count {{ font-family: 'Outfit', sans-serif; font-size: 4rem; font-weight: 600; color: var(--accent-color); }}

            .status-indicator {{
                display: flex; align-items: center; justify-content: center; font-size: 0.8rem; color: var(--success-color);
                margin-bottom: 1.2rem; font-weight: 700; letter-spacing: 0.08em;
            }}

            .dot {{
                width: 8px; height: 8px; background-color: var(--success-color); border-radius: 50%;
                margin-right: 10px; box-shadow: 0 0 15px rgba(40, 205, 65, 0.3); animation: pulse 2.5s infinite;
            }}

            @keyframes pulse {{
                0% {{ opacity: 1; transform: scale(1); }}
                50% {{ opacity: 0.6; transform: scale(0.9); }}
                100% {{ opacity: 1; transform: scale(1); }}
            }}

            .footer {{ margin-top: 2.5rem; font-size: 0.75rem; color: var(--text-secondary); letter-spacing: 0.25em; font-weight: 500; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="main-card">
                <div class="status-indicator">
                    <span class="dot"></span> SYSTEM OPERATIONAL
                </div>
                <h1>Oracle One</h1>
                
                <div class="grid-stats">
                    <div class="stat-box">
                        <div class="stat-label">CPU</div>
                        <div class="stat-value">{cpu_usage}%</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Memory</div>
                        <div class="stat-value">{memory_usage}%</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Uptime</div>
                        <div class="stat-value">{uptime}</div>
                    </div>
                </div>

                <div class="menu-section">
                    <a href="/kfcc" class="menu-button">
                        <div class="icon">🏦</div>
                        <div class="text">
                            <div class="title">새마을금고 금리조회</div>
                            <div class="subtitle">내 서버 전용 실시간 금리 API 탑재</div>
                        </div>
                        <div class="arrow">→</div>
                    </a>
                </div>

                <div class="visits-section">
                    <div class="visits-label">TOTAL INTERACTIONS</div>
                    <div class="visits-count">{visits}</div>
                </div>
            </div>
            <div style="text-align: center;">
                <div class="footer">POWERED BY ORACLE CLOUD & FASTAPI</div>
            </div>
        </div>
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

@app.get("/health")
def health_check():
    return {"status": "ok"}
