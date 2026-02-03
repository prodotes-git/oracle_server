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
import local_currency

app = FastAPI()

# 라우터 연결
app.include_router(card_events.router)
app.include_router(kfcc.router)
app.include_router(local_currency.router)

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
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>inbestlab</title>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --apple-bg: #ffffff;
                --apple-text: #1d1d1f;
                --apple-blue: #0066cc;
                --nav-bg: rgba(255, 255, 255, 0.8);
                --card-bg: #f5f5f7;
                --secondary-text: #86868b;
                --border-color: rgba(0, 0, 0, 0.1);
            }}

            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                background-color: var(--apple-bg);
                color: var(--apple-text);
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro KR", "SF Pro Display", "Noto Sans KR", sans-serif;
                -webkit-font-smoothing: antialiased;
                line-height: 1.47059;
            }}

            nav {{
                position: fixed; top: 0; width: 100%; height: 44px;
                background: var(--nav-bg); backdrop-filter: saturate(180%) blur(20px);
                z-index: 9999; border-bottom: 1px solid rgba(0,0,0,0.1);
            }}
            .nav-content {{
                max-width: 1024px; margin: 0 auto; height: 100%;
                display: flex; align-items: center; justify-content: space-between;
                padding: 0 22px; font-weight: 400; font-size: 12px;
                letter-spacing: -0.01em;
            }}
            .nav-logo {{ font-weight: 600; font-size: 17px; cursor: default; }}

            .hero {{
                padding-top: 120px;
                text-align: center;
                max-width: 800px;
                margin: 0 auto 80px auto;
            }}
            .hero-title {{
                font-size: 56px; line-height: 1.07143; font-weight: 700;
                letter-spacing: -0.005em; margin-bottom: 15px;
            }}
            .hero-subtitle {{
                font-size: 24px; line-height: 1.16667; font-weight: 400;
                letter-spacing: .009em; color: var(--secondary-text);
            }}

            .dashboard-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                max-width: 1200px;
                margin: 0 auto 100px auto;
                padding: 0 22px;
            }}

            .bento-card {{
                background: var(--card-bg);
                border-radius: 18px;
                padding: 30px;
                text-decoration: none;
                color: inherit;
                transition: transform 0.3s ease;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                min-height: 280px;
                overflow: hidden;
                border: 1px solid var(--border-color);
            }}
            .bento-card:hover {{
                transform: scale(1.01);
            }}

            .card-label {{
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 5px;
            }}
            .card-value {{
                font-size: 28px;
                font-weight: 700;
                letter-spacing: -0.02em;
                margin-bottom: 12px;
                line-height: 1.2;
            }}
            .card-desc {{
                font-size: 15px;
                color: var(--secondary-text);
                line-height: 1.4;
                font-weight: 400;
            }}
            
            .explore {{ 
                margin-top: 30px; 
                color: var(--apple-blue); 
                font-size: 17px;
                font-weight: 400;
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            .explore:hover {{ text-decoration: underline; }}

            @media (max-width: 1024px) {{
                .dashboard-grid {{ grid-template-columns: repeat(2, 1fr); }}
            }}

            @media (max-width: 734px) {{
                .hero-title {{ font-size: 40px; }}
                .hero-subtitle {{ font-size: 19px; }}
                .dashboard-grid {{ grid-template-columns: 1fr; }}
                .bento-card {{ min-height: 240px; padding: 25px; }}
                .card-value {{ font-size: 24px; }}
            }}
        </style>
    </head>
    <body>
        <nav>
            <div class="nav-content">
                <div class="nav-logo">inbestlab</div>
                <div style="color: var(--secondary-text);">지능형 금융 서비스</div>
            </div>
        </nav>

        <section class="hero">
            <h1 class="hero-title">더 스마트한 금융의 시작</h1>
            <p class="hero-subtitle">실시간 데이터 분석을 통한 인사이트를 경험해보세요.</p>
        </section>

        <div class="dashboard-grid">
            <a href="/card-events" class="bento-card">
                <div>
                    <div class="card-label">카드 혜택 정렬</div>
                    <div class="card-value">모든 카드사 이벤트</div>
                    <div class="card-desc">주요 카드사의 프로모션과 혜택을 한눈에 확인하고 나에게 맞는 혜택을 찾아보세요.</div>
                </div>
                <div class="explore">더 알아보기 <span>></span></div>
            </a>

            <a href="/kfcc" class="bento-card" style="background-color: #000; color: #fff;">
                <div>
                    <div class="card-label" style="color: rgba(255,255,255,0.7);">금리 추적</div>
                    <div class="card-value">새마을금고 금리 지표</div>
                    <div class="card-desc" style="color: rgba(255,255,255,0.8);">전국의 새마을금고 예적금 금리를 실시간으로 비교하고 최적의 투자처를 발견하세요.</div>
                </div>
                <div class="explore" style="color: #0066cc;">데이터 확인하기 <span>></span></div>
            </a>

            <a href="/local-currency" class="bento-card" style="background: linear-gradient(135deg, #fff 0%, #f0f0f0 100%);">
                <div>
                    <div class="card-label">지역 경제 활성화</div>
                    <div class="card-value">온누리 & 경기지역화폐</div>
                    <div class="card-desc">내 주변의 온누리상품권 및 경기지역화폐 가맹점을 지도로 쉽고 빠르게 찾아보세요.</div>
                </div>
                <div class="explore">지도에서 찾기 <span>></span></div>
            </a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- 스케줄러 설정 ---
# misfire_grace_time을 설정하여 서버 재시작 시점에 밀린 작업들이 한꺼번에 실행되어 메모리 부족(OOM)으로 크래시되는 것을 방지합니다.
job_defaults = {
    'misfire_grace_time': 300, # 5분 이상 지연된 작업은 무시
    'coalesce': True,
    'max_instances': 1
}
scheduler = AsyncIOScheduler(timezone=seoul_tz, job_defaults=job_defaults)

@app.on_event("startup")
async def start_scheduler():
    # 데이터베이스 초기화 (비동기 스레드 실행, 부팅 지연 최소화)
    import threading
    threading.Thread(target=local_currency.init_db, daemon=True).start()
    
    # [주의] 서버 부팅 시 즉시 데이터 수집을 시작하지 않습니다.
    # 모든 수집은 지정된 크론 시간(새벽 4시) 또는 사용자의 수동 요청에 의해서만 실행됩니다.
    
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
    
    # 메모리 사용량 로깅
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / 1024 / 1024
    print(f"Scheduler started. Current Memory Usage: {mem_mb:.2f} MB")
    print("All tasks are scheduled for 04:00 AM. No immediate sync on startup.")
