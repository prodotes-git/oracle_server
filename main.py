import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
import os
import psutil
import time
import json
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 모듈별 라우터 및 유틸리티 임포트
from shared import r, seoul_tz, CACHE_EXPIRE, boot_time, get_cached_data
import card_events
import kfcc

app = FastAPI()

# 라우터 연결
app.include_router(card_events.router)
app.include_router(kfcc.router)

# --- 공통 라우터 (대시보드, 헬스체크) ---

def get_uptime():
    uptime_seconds = int(time.time() - boot_time)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0: return f"{days}d {hours}h"
    return f"{hours}h {minutes}m"

@app.get("/health")
async def health_check():
    return {"status": "ok", "uptime": get_uptime()}

@app.get("/", response_class=HTMLResponse)
def read_root():
    try: visits = r.incr("counter") if r else "---"
    except: visits = "---"
    cpu = psutil.cpu_percent(); mem = psutil.virtual_memory().percent
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Oracle Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;500;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --apple-bg: #f5f5f7;
                --apple-text: #1d1d1f;
                --apple-blue: #0071e3;
                --nav-bg: rgba(255, 255, 255, 0.72);
                --card-bg: #ffffff;
                --card-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}

            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                background-color: var(--apple-bg);
                color: var(--apple-text);
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                -webkit-font-smoothing: antialiased;
                line-height: 1.47059;
            }}

            /* Apple Navigation Bar */
            nav {{
                position: fixed; top: 0; width: 100%; height: 50px;
                background: var(--nav-bg); backdrop-filter: saturate(180%) blur(20px);
                z-index: 9999; border-bottom: 1px solid rgba(0,0,0,0.08);
            }}
            .nav-content {{
                max-width: 980px; margin: 0 auto; height: 100%;
                display: flex; align-items: center; justify-content: space-between;
                padding: 0 20px; font-weight: 500; font-size: 14px;
            }}

            .hero {{
                padding-top: 100px;
                text-align: center;
                max-width: 800px;
                margin: 0 auto 60px auto;
            }}
            .hero-label {{
                font-size: 21px; font-weight: 600; color: var(--apple-blue); margin-bottom: 10px;
                letter-spacing: -0.01em;
            }}
            .hero-title {{
                font-size: 56px; line-height: 1.07143; font-weight: 700;
                letter-spacing: -0.005em; font-family: 'Outfit';
            }}
            .hero-subtitle {{
                font-size: 24px; line-height: 1.16667; font-weight: 400;
                letter-spacing: .009em; margin-top: 15px; color: #86868b;
            }}

            .dashboard-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.5rem;
                max-width: 1000px;
                margin: 0 auto 100px auto;
                padding: 0 20px;
            }}

            .bento-card {{
                background: var(--card-bg);
                border-radius: 20px;
                padding: 2.5rem;
                text-decoration: none;
                color: inherit;
                transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.4s ease;
                display: flex;
                flex-direction: column;
                justify-content: center;
                box-shadow: var(--card-shadow);
                position: relative;
                overflow: hidden;
            }}
            .bento-card:hover {{
                transform: scale(1.02);
                box-shadow: 0 20px 40px rgba(0,0,0,0.08);
            }}

            .card-label {{
                font-size: 12px;
                color: #86868b;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                font-weight: 600;
                margin-bottom: 8px;
            }}
            .card-value {{
                font-size: 2.8rem;
                font-weight: 700;
                color: var(--apple-text);
                font-family: 'Outfit';
            }}
            .card-desc {{
                font-size: 1rem;
                color: #86868b;
                margin-top: 10px;
            }}
            
            .service-link {{
                background: #000;
                color: #fff;
            }}
            .service-link .card-value {{ color: #fff; }}
            .service-link .explore {{ 
                margin-top: 20px; 
                color: var(--apple-blue); 
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 5px;
            }}

            @media (max-width: 734px) {{
                .hero-title {{ font-size: 40px; }}
                .hero-subtitle {{ font-size: 21px; }}
                .card-value {{ font-size: 2rem; }}
            }}
        </style>
    </head>
    <body>
        <nav>
            <div class="nav-content">
                <div>Oracle Intelligence</div>
                <div style="color: #86868b;">Enterprise Systems</div>
            </div>
        </nav>

        <section class="hero">
            <div class="hero-label">System Performance</div>
            <h1 class="hero-title">Intelligent Oracle Dashboard</h1>
            <p class="hero-subtitle">Real-time financial data and system health tracking.</p>
        </section>

        <div class="dashboard-grid">
            <div class="bento-card">
                <div class="card-label">CPU LOAD</div>
                <div class="card-value">{cpu}%</div>
                <div class="card-desc">System computing resources.</div>
            </div>
            <div class="bento-card">
                <div class="card-label">MEMORY USAGE</div>
                <div class="card-value">{mem}%</div>
                <div class="card-desc">Dynamic RAM optimization active.</div>
            </div>
            <div class="bento-card">
                <div class="card-label">UPTIME</div>
                <div class="card-value">{get_uptime()}</div>
                <div class="card-desc">Stable server operation.</div>
            </div>
            
            <a href="/card-events" class="bento-card service-link">
                <div class="card-label">ACTIVE SERVICE</div>
                <div class="card-value">Card Events</div>
                <div class="card-desc">Integrated promotion tracker.</div>
                <div class="explore">Explore Promotions <span>↗</span></div>
            </a>

            <a href="/kfcc" class="bento-card service-link" style="background: linear-gradient(135deg, #0046ff, #0071e3);">
                <div class="card-label" style="color: rgba(255,255,255,0.7);">FINANCE SERVICE</div>
                <div class="card-value">KFCC Rates</div>
                <div class="card-desc" style="color: rgba(255,255,255,0.8);">Real-time interest tracker.</div>
                <div class="explore" style="color: #fff;">Check Rates <span>↗</span></div>
            </a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- 스케줄러 설정 ---
scheduler = AsyncIOScheduler(timezone=seoul_tz)

@app.on_event("startup")
async def start_scheduler():
    # 매일 새벽 4시부터 순차적 실행
    scheduler.add_job(kfcc.background_crawl_kfcc, 'cron', hour=4, minute=0)
    scheduler.add_job(card_events.crawl_shinhan_bg, 'cron', hour=4, minute=5)
    scheduler.add_job(card_events.crawl_kb_bg, 'cron', hour=4, minute=10)
    scheduler.add_job(card_events.crawl_hana_bg, 'cron', hour=4, minute=15)
    scheduler.add_job(card_events.crawl_woori_bg, 'cron', hour=4, minute=20)
    scheduler.add_job(card_events.crawl_bc_bg, 'cron', hour=4, minute=25)
    scheduler.add_job(card_events.crawl_samsung_bg, 'cron', hour=4, minute=30)
    scheduler.add_job(card_events.crawl_hyundai_bg, 'cron', hour=4, minute=35)
    scheduler.add_job(card_events.crawl_lotte_bg, 'cron', hour=4, minute=40)
    scheduler.start()
    print("Scheduler started. All tasks scheduled.")
