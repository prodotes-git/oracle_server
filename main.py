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
        <title>Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700&display=swap" rel="stylesheet">
        <style>
            :root {{ --bg: #f5f5f7; --card-bg: rgba(255, 255, 255, 0.82); --text: #1d1d1f; --accent: #0071e3; }}
            body {{ background: var(--bg); font-family: -apple-system, sans-serif; padding: 4vw; }}
            .dashboard-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; max-width: 1200px; margin: 0 auto; }}
            .bento-card {{ background: var(--card-bg); backdrop-filter: blur(20px); border-radius: 24px; padding: 2rem; text-decoration: none; color: inherit; transition: 0.3s; }}
            .bento-card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
            .card-label {{ font-size: 0.8rem; color: #86868b; text-transform: uppercase; }}
            .card-value {{ font-size: 2.5rem; font-weight: 700; margin: 0.5rem 0; font-family: 'Outfit'; }}
        </style>
    </head>
    <body>
        <h1>System Overview</h1>
        <div class="dashboard-grid">
            <div class="bento-card">
                <div class="card-label">CPU Usage</div>
                <div class="card-value">{cpu}%</div>
            </div>
            <div class="bento-card">
                <div class="card-label">Memory</div>
                <div class="card-value">{mem}%</div>
            </div>
            <div class="bento-card">
                <div class="card-label">Uptime</div>
                <div class="card-value">{get_uptime()}</div>
            </div>
            <a href="/card-events" class="bento-card">
                <div class="card-label">Services</div>
                <div class="card-value">Card Events</div>
                <div style="color:var(--accent)">Explore ↗</div>
            </a>
            <a href="/kfcc" class="bento-card">
                <div class="card-label">Services</div>
                <div class="card-value">KFCC Rates</div>
                <div style="color:var(--accent)">Explore ↗</div>
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
