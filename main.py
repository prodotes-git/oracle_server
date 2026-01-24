from fastapi import FastAPI
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

def get_uptime():
    uptime_seconds = int(time.time() - boot_time)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m"

@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        visits = r.incr("counter")
    except Exception:
        visits = "---"
    
    # 시스템 정보 가져오기
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
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                -webkit-font-smoothing: antialiased;
            }}
            
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

            .container {{
                width: 100%;
                max-width: 600px;
                animation: fadeIn 1.2s cubic-bezier(0.2, 0.8, 0.2, 1);
            }}

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

            .grid-stats {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1.2rem;
                margin-top: 1rem;
            }}

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

            .stat-value {{
                font-family: 'Outfit', sans-serif;
                font-size: 1.6rem;
                font-weight: 600;
                color: var(--accent-color);
            }}

            .visits-section {{
                margin-top: 3.5rem;
                border-top: 1px solid rgba(0, 0, 0, 0.05);
                padding-top: 2.5rem;
            }}

            .visits-label {{
                font-size: 0.9rem;
                color: var(--text-secondary);
                margin-bottom: 0.8rem;
                font-weight: 400;
                letter-spacing: 0.02em;
            }}

            .visits-count {{
                font-family: 'Outfit', sans-serif;
                font-size: 4rem;
                font-weight: 600;
                color: var(--accent-color);
                letter-spacing: -0.02em;
            }}

            .status-indicator {{
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.8rem;
                color: var(--success-color);
                margin-bottom: 1.2rem;
                font-weight: 700;
                letter-spacing: 0.08em;
            }}

            .dot {{
                width: 8px;
                height: 8px;
                background-color: var(--success-color);
                border-radius: 50%;
                margin-right: 10px;
                box-shadow: 0 0 15px rgba(40, 205, 65, 0.3);
                animation: pulse 2.5s infinite;
            }}

            @keyframes pulse {{
                0% {{ opacity: 1; transform: scale(1); }}
                50% {{ opacity: 0.6; transform: scale(0.9); }}
                100% {{ opacity: 1; transform: scale(1); }}
            }}

            .footer {{
                margin-top: 2.5rem;
                font-size: 0.75rem;
                color: var(--text-secondary);
                letter-spacing: 0.25em;
                font-weight: 500;
            }}
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

@app.get("/health")
def health_check():
    return {"status": "ok"}
