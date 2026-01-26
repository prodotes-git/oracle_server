from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
import os
import json
from datetime import datetime
from shared import r, seoul_tz, CACHE_EXPIRE

router = APIRouter()

KFCC_CACHE_KEY = "kfcc_rates_cache_v1"

@router.get("/api/kfcc")
async def get_kfcc_data():
    try:
        if r:
            cached = r.get(KFCC_CACHE_KEY)
            if cached: return json.loads(cached)
        
        local_path = "kfcc_data.json"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mtime = os.path.getmtime(local_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            res = {"last_updated": last_updated, "data": data}
            if r: r.setex(KFCC_CACHE_KEY, CACHE_EXPIRE, json.dumps(res))
            return res
        return {"last_updated": None, "message": "데이터가 없습니다.", "data": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/kfcc", response_class=HTMLResponse)
def view_kfcc_page():
    try:
        # Assuming kfcc.html is in the templates folder for consistency
        path = os.path.join("templates", "kfcc.html")
        if not os.path.exists(path):
            # Fallback to root directory if not found in templates
            path = "kfcc.html"
            
        with open(path, "r", encoding="utf-8") as f: return f.read()
    except: return "kfcc.html not found"

@router.post("/api/kfcc/update")
async def update_kfcc_data(background_tasks: BackgroundTasks):
    background_tasks.add_task(background_crawl_kfcc)
    return {"status": "started"}

async def background_crawl_kfcc():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting KFCC background crawl...")
        from kfcc_crawler import run_crawler
        data = await run_crawler()
        if not data: return
        current_time = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
        save_data = {"last_updated": current_time, "data": data}
        with open("kfcc_data.json", "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        if r: r.setex(KFCC_CACHE_KEY, CACHE_EXPIRE, json.dumps(save_data))
        print(f"[{datetime.now(seoul_tz)}] KFCC crawl finished.")
    except Exception as e: print(f"KFCC crawl failed: {e}")
