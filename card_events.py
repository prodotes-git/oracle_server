import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
import os
import json
import ssl
from datetime import datetime
from bs4 import BeautifulSoup
import re
from shared import r, seoul_tz, CACHE_EXPIRE, get_cached_data

router = APIRouter()

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

def render_template(filename: str):
    path = os.path.join("templates", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Template {filename} not found"

# --- API Endpoints ---
@router.get("/api/shinhan-myshop")
async def get_shinhan_myshop():
    try:
        if r:
            cached = r.get(SHINHAN_MYSHOP_CACHE_KEY)
            if cached: return json.loads(cached)
        api_url = "https://www.shinhancard.com/mob/MOBFM501N/MOBFM501R21.ajax"
        base_url = "https://www.shinhancard.com"
        headers = {
            "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc", "Origin": base_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            await client.get(f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc", headers={"User-Agent": headers["User-Agent"]})
            response = await client.post(api_url, json={"QY_CCD": "T"}, headers=headers)
            if response.status_code == 200:
                data = response.json(); msg = data.get("mbw_message")
                if isinstance(msg, dict):
                    grid = msg.get("GRID1", {}); all_coupons = []; seen = set()
                    for i in range(len(grid.get("SSG_NM", []))):
                        name = grid["SSG_NM"][i]; benefit = grid["MCT_CRD_SV_RG_TT"][i] if i < len(grid["MCT_CRD_SV_RG_TT"]) else ""
                        full_name = f"[{name}] {benefit}".strip()
                        if full_name in seen: continue
                        seen.add(full_name)
                        img = grid["MYH_CUP_IMG_URL_AR"][i] if i < len(grid["MYH_CUP_IMG_URL_AR"]) else ""
                        if img and not img.startswith('http'): img = f"{base_url}{img}"
                        link = grid["MYH_SRM_ONL_SPP_MLL_URL_AR"][i] if i < len(grid["MYH_SRM_ONL_SPP_MLL_URL_AR"]) else f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc"
                        if link and not link.startswith('http'): link = f"{base_url}{link}"
                        end = grid["MCT_PLF_MO_EDD"][i] if i < len(grid["MCT_PLF_MO_EDD"]) else ""
                        if len(end) == 8: end = f"~ {end[:4]}.{end[4:6]}.{end[6:]}"
                        all_coupons.append({"category": "마이샵 쿠폰", "eventName": full_name, "period": end, "link": link, "image": img, "bgColor": "#ffffff"})
                    res = {"data": all_coupons}
                    if r: r.setex(SHINHAN_MYSHOP_CACHE_KEY, CACHE_EXPIRE, json.dumps(res))
                    return res
        return {"data": []}
    except Exception as e: print(f"Shinhan MyShop API Error: {e}"); return {"data": []}

@router.get("/api/shinhan-cards")
async def get_shinhan_cards(): return get_cached_data(SHINHAN_CACHE_KEY, os.path.join(os.getcwd(), 'shinhan_data.json'))
@router.get("/api/shinhan-myshop")
async def get_shinhan_myshop(): return get_cached_data(SHINHAN_MYSHOP_CACHE_KEY, os.path.join(os.getcwd(), 'shinhan_myshop_data.json'))
@router.get("/api/kb-cards")
async def get_kb_cards(): return get_cached_data(KB_CACHE_KEY, os.path.join(os.getcwd(), 'kb_data.json'))
@router.get("/api/hana-cards")
async def get_hana_cards(): return get_cached_data(HANA_CACHE_KEY, os.path.join(os.getcwd(), 'hana_data.json'))
@router.get("/api/woori-cards")
async def get_woori_cards(): return get_cached_data(WOORI_CACHE_KEY, os.path.join(os.getcwd(), 'woori_data.json'))
@router.get("/api/bc-cards")
async def get_bc_cards(): return get_cached_data(BC_CACHE_KEY, os.path.join(os.getcwd(), 'bc_data.json'))
@router.get("/api/samsung-cards")
async def get_samsung_cards(): return get_cached_data(SAMSUNG_CACHE_KEY, os.path.join(os.getcwd(), 'samsung_data.json'))
@router.get("/api/hyundai-cards")
async def get_hyundai_cards(): return get_cached_data(HYUNDAI_CACHE_KEY, os.path.join(os.getcwd(), "hyundai_data.json"))
@router.get("/api/lotte-cards")
async def get_lotte_cards(): return get_cached_data(LOTTE_CACHE_KEY, os.path.join(os.getcwd(), "lotte_data.json"))

# --- 통합 업데이트 API (이름 기반) ---
@router.post("/api/card-update/{card_name}")
async def unified_card_update(card_name: str, bg_tasks: BackgroundTasks):
    crawlers = {
        "shinhan": crawl_shinhan_bg,
        "kb": crawl_kb_bg,
        "hana": crawl_hana_bg,
        "woori": crawl_woori_bg,
        "bc": crawl_bc_bg,
        "samsung": crawl_samsung_bg,
        "hyundai": crawl_hyundai_bg,
        "lotte": crawl_lotte_bg
    }
    
    card_name = card_name.lower().strip().replace("-cards", "").replace("-card", "")
    if card_name in crawlers:
        print(f"[{datetime.now(seoul_tz)}] Manual update STARTED for: {card_name}")
        bg_tasks.add_task(crawlers[card_name])
        return {"status": "started", "card": card_name, "message": "Background task initiated."}
    
    print(f"[{datetime.now(seoul_tz)}] Manual update FAILED: Card '{card_name}' not found")
    raise HTTPException(status_code=404, detail=f"Card '{card_name}' not found")

# 구버전 호환성을 위한 개별 엔드포인트 유지
@router.post("/api/shinhan/update")
async def update_shinhan(bg_tasks: BackgroundTasks): return await unified_card_update("shinhan", bg_tasks)
@router.post("/api/kb/update")
async def update_kb(bg_tasks: BackgroundTasks): return await unified_card_update("kb", bg_tasks)
@router.post("/api/hana/update")
async def update_hana(bg_tasks: BackgroundTasks): return await unified_card_update("hana", bg_tasks)
@router.post("/api/woori/update")
async def update_woori(bg_tasks: BackgroundTasks): return await unified_card_update("woori", bg_tasks)
@router.post("/api/bc/update")
async def update_bc(bg_tasks: BackgroundTasks): return await unified_card_update("bc", bg_tasks)
@router.post("/api/samsung/update")
async def update_samsung(bg_tasks: BackgroundTasks): return await unified_card_update("samsung", bg_tasks)
@router.post("/api/hyundai/update")
async def update_hyundai(bg_tasks: BackgroundTasks): return await unified_card_update("hyundai", bg_tasks)
@router.post("/api/lotte/update")
async def update_lotte(bg_tasks: BackgroundTasks): return await unified_card_update("lotte", bg_tasks)

# --- Crawl Background Tasks ---
async def crawl_shinhan_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Shinhan background crawl...")
        all_events = []; seen = set(); base_url = "https://www.shinhancard.com"
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            for i in range(1, 10):
                try:
                    res = await client.get(f"{base_url}/logic/json/evnPgsList0{i}.json", headers={"User-Agent":"Mozilla/5.0","Referer":base_url})
                    if res.status_code != 200: continue
                    for ev in res.json().get("root",{}).get("evnlist",[]):
                        title = f"{ev.get('mobWbEvtNm','')} ({ev.get('evtImgSlTilNm','')})".strip() if ev.get('evtImgSlTilNm') else ev.get('mobWbEvtNm','').strip()
                        if not title or title in seen: continue
                        seen.add(title); s, e = ev.get('mobWbEvtStd',''), ev.get('mobWbEvtEdd','')
                        if len(s)==8: s=f"{s[:4]}.{s[4:6]}.{s[6:]}"
                        if len(e)==8: e=f"{e[:4]}.{e[4:6]}.{e[6:]}"
                        img = ev.get('hpgEvtCtgImgUrlAr',''); link = ev.get('hpgEvtDlPgeUrlAr','')
                        if img and not img.startswith('http'): img = f"{base_url}{img}"
                        if link and not link.startswith('http'): link = f"{base_url}{link}"
                        all_events.append({"category":ev.get('hpgEvtKindNm','이벤트'), "eventName":title, "period":f"{s} ~ {e}", "link":link, "image":img, "bgColor":"#ffffff"})
                except: continue
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "shinhan_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(SHINHAN_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] Shinhan crawl finished: {len(all_events)} events saved.")
        else:
            print(f"[{datetime.now(seoul_tz)}] Shinhan crawl finished: No events found.")
    except Exception as e: print(f"Shinhan crawl error: {e}")

async def crawl_hana_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Hana background crawl...")
        all_events = []; base_url = "https://m.hanacard.co.kr"; api_url = f"{base_url}/MKEVT1000M.ajax"
        
        # Hana Card server has SSL compatibility issues (DH_KEY_TOO_SMALL).
        # We use a custom SSL context with lower security level to allow the connection.
        ctx = ssl.create_default_context()
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except:
            # Fallback for systems where SECLEVEL might not be supported exactly like this
            ctx.set_ciphers('HIGH:!DH:!aNULL')
            
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        async with httpx.AsyncClient(timeout=30.0, verify=ctx) as client:
            for page in range(1, 40):
                try:
                    res = await client.post(api_url, data={"page":str(page)}, headers={"User-Agent":"Mozilla/5.0","Referer":f"{base_url}/MKEVT1000M.web"})
                    if res.status_code != 200: break
                    try: text = res.content.decode("euc-kr")
                    except: text = res.text
                    data = json.loads(text); emap = data.get("DATA",{}).get("eventListMap",{}); elist = emap.get("list",[])
                    if not elist: break
                    for ev in elist:
                        img = f"{base_url}{ev.get('APN_FILE_NM')}" if ev.get('APN_FILE_NM') and not ev.get('APN_FILE_NM').startswith('http') else ev.get('APN_FILE_NM')
                        all_events.append({"category":ev.get("ITG_APP_EVN_MC_NM","이벤트"), "eventName":ev.get("EVN_TIT_NM","").strip(), "period":f"{ev.get('EVN_SDT','')} ~ {ev.get('EVN_EDT','')}", "link":f"{base_url}/MKEVT1010M.web?EVN_SEQ={ev.get('EVN_SEQ')}", "image":img, "bgColor":"#ffffff"})
                    if page >= int(emap.get("totalPage", 0)): break
                except Exception as e: 
                    print(f"Hana crawl page {page} error: {e}")
                    break
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "hana_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(HANA_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] Hana crawl finished: {len(all_events)} events saved.")
    except Exception as e: print(f"Hana crawl error: {e}")

async def crawl_kb_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting KB background crawl (Playwright)...")
        from playwright.async_api import async_playwright
        all_events = []; seen = set()
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")
            page = await ctx.new_page()
            try:
                # KB Card event list page - FIXED URL
                print(f"[{datetime.now(seoul_tz)}] KB - Navigating to CORRECT list page: https://m.kbcard.com/BON/DVIEW/MBBV0002")
                try:
                    await page.goto("https://m.kbcard.com/BON/DVIEW/MBBV0002", timeout=60000, wait_until="load")
                except Exception as e:
                    print(f"KB goto error: {e}")
                
                await page.wait_for_timeout(10000)
                
                # Check for popups (Common on KB site)
                try:
                    await page.click('button:has-text("확인"), .btn_confirm, #pop_confirm', timeout=3000)
                    print(f"[{datetime.now(seoul_tz)}] KB - Popup/Confirm clicked.")
                except: pass

                # Extracting with refined selectors for the MBBV0002 page
                res = await page.evaluate('''() => {
                    const items = document.querySelectorAll('.event-list__item, li.event-list__item, a[href^="javascript:goDetail"], .list_type2 li, .event_list li');
                    return Array.from(items).map(el => {
                        let li = el.closest('li') || el;
                        const titleEl = li.querySelector('.tit, dt, strong, .event-list__title, h2, h3, p');
                        const periodEl = li.querySelector('.date, .period, dd, .event-list__date, .time');
                        const imgEl = li.querySelector('img');
                        const linkEl = li.querySelector('a');
                        if(!titleEl || titleEl.innerText.length < 2) return null;
                        return {
                            title: titleEl.innerText.trim(),
                            period: periodEl ? periodEl.innerText.trim() : "",
                            image: imgEl ? imgEl.src : "",
                            link: linkEl ? linkEl.href : ""
                        };
                    }).filter(x => x && x.title && x.title.length > 2);
                }''')
                
                print(f"[{datetime.now(seoul_tz)}] KB - Extracted {len(res)} candidate events.")
                
                for ev in res:
                    if ev['title'] in seen: continue
                    seen.add(ev['title'])
                    all_events.append({
                        "category": "KB국민카드",
                        "eventName": ev['title'],
                        "period": ev['period'],
                        "link": ev['link'],
                        "image": ev['image'],
                        "bgColor": "#ffffff"
                    })
            except Exception as e: print(f"KB PW error: {e}")
            finally: await browser.close()
            
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "kb_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(KB_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] KB crawl finished: {len(all_events)} events saved.")
    except Exception as e: print(f"KB crawl error: {e}")

async def crawl_woori_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Woori background crawl...")
        from playwright.async_api import async_playwright
        all_events = []; base_url = "https://m.wooricard.com"
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent="Mozilla/5.0"); page = await ctx.new_page()
            try:
                # Use expect_response context manager for Woori Card
                async with page.expect_response(lambda r: "getPrgEvntList.pwkjson" in r.url, timeout=30000) as resp_info:
                    await page.goto(f"{base_url}/dcmw/yh1/bnf/bnf02/prgevnt/M1BNF202S00.do", timeout=60000)
                res = await resp_info.value
                data = await res.json(); events = data.get('prgEvntList', [])
                for ev in events:
                    title = (ev.get('cardEvntNm') or ev.get('mblDocTitlTxt')).strip(); s, e = ev.get('evntSdt',''), ev.get('evntEdt','')
                    if len(s)==8: s=f"{s[:4]}.{s[4:6]}.{s[6:]}"
                    if len(e)==8: e=f"{e[:4]}.{e[4:6]}.{e[6:]}"
                    img = f"{base_url}{ev.get('fileCoursWeb')}" if ev.get('fileCoursWeb') and not ev.get('fileCoursWeb').startswith('http') else ev.get('fileCoursWeb')
                    link = f"https://pc.wooricard.com/dcpc/yh1/bnf/bnf02/prgevnt/H1BNF202S01.do?evntSrno={ev.get('evntSrno')}" if ev.get('evntSrno') else base_url
                    all_events.append({"category":"우리카드", "eventName":title, "period":f"{s} ~ {e}", "link":link, "image":img, "bgColor":"#007bc3"})
            except Exception as e: print(f"Woori PW error: {e}")
            finally: await browser.close()
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "woori_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(WOORI_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] Woori crawl finished: {len(all_events)} events saved.")
        else:
            print(f"[{datetime.now(seoul_tz)}] Woori crawl finished: No events found.")
    except Exception as e: print(f"Woori crawl error: {e}")

async def crawl_bc_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting BC background crawl...")
        all_events = []; base_url = "https://web.paybooc.co.kr"; api_url = f"{base_url}/web/evnt/lst-evnt-data"
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            for pg in range(1, 10):
                try:
                    res = await client.get(api_url, params={"reqType":"init" if pg==1 else "more", "inqrDv":"ING", "pgeNo":str(pg), "pgeCnt":"20", "ordering":"RECENT"}, headers={"User-Agent":"Mozilla/5.0"})
                    if res.status_code != 200: break
                    elist = res.json().get("data", {}).get("evntInqrList", [])
                    if not elist: break
                    for ev in elist:
                        title = " ".join([ev.get(f"pybcUnifEvntNm{i}","") for i in range(1,4)]).strip(); s, e = ev.get("evntBltnStrtDtm",""), ev.get("evntBltnEndDtm","")
                        if len(s)>=8: s=f"{s[:4]}.{s[4:6]}.{s[6:8]}"
                        if len(e)>=8: e=f"{e[:4]}.{e[4:6]}.{e[6:8]}"
                        all_events.append({"category":"BC카드", "eventName":title, "period":f"{s} ~ {e}", "link":f"{base_url}/web/evnt/evnt-dts?pybcUnifEvntNo={ev.get('pybcUnifEvntNo')}", "image":ev.get("evntBsImgUrlAddr"), "bgColor":ev.get("evntBsBgColrVal","#ffffff")})
                except: break
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "bc_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(BC_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] BC crawl finished: {len(all_events)} events saved.")
        else:
            print(f"[{datetime.now(seoul_tz)}] BC crawl finished: No events found.")
    except Exception as e: print(f"BC crawl error: {e}")

async def crawl_samsung_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Samsung background crawl...")
        from playwright.async_api import async_playwright
        all_events = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")
            page = await ctx.new_page()
            try:
                await page.goto("https://m.samsungcard.com/personal/event/ing/UHPPBE1401M0.jsp", timeout=90000, wait_until="domcontentloaded")
                await page.wait_for_timeout(10000)
                res = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('li')).map(li => {
                        const img = li.querySelector('img'), a = li.querySelector('a');
                        if(!img || !a) return null;
                        const text = li.innerText.replace(/\\n/g,' ').trim();
                        const dm = text.match(/(\\d{4}\\.\\d{2}\\.\\d{2})\\s*~\\s*(\\d{4}\\.\\d{2}\\.\\d{2})/);
                        const idm = (a.getAttribute('onclick')||"").match(/GoDtlBrws\\(['"](\\d+)['"]/);
                        if(dm && idm) return {title:text.replace(dm[0],'').substring(0,100).trim(), period:dm[0], image:img.src, id:idm[1]};
                        return null;
                    }).filter(x=>x);
                }''')
                for ev in res:
                    all_events.append({"category":"삼성카드", "eventName":ev['title'], "period":ev['period'], "link":f"https://www.samsungcard.com/personal/event/ing/UHPPBE1403M0.jsp?cms_id={ev['id']}", "image":ev['image'], "bgColor":"#0056b3"})
            except Exception as e: print(f"Samsung PW error: {e}")
            finally: await browser.close()
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "samsung_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(SAMSUNG_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] Samsung crawl finished: {len(all_events)} events saved.")
        else:
            print(f"[{datetime.now(seoul_tz)}] Samsung crawl finished: No events found.")
    except Exception as e: print(f"Samsung crawl error: {e}")

async def crawl_hyundai_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Hyundai background crawl...")
        from playwright.async_api import async_playwright
        all_events = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")
            page = await ctx.new_page()
            try:
                await page.goto("https://www.hyundaicard.com/cpb/ev/CPBEV0101_01.hc", timeout=90000, wait_until="domcontentloaded")
                await page.wait_for_timeout(10000)
                res = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('li')).map(li => {
                        const img = li.querySelector('img'), a = li.querySelector('a');
                        if(!img) return null;
                        const text = li.innerText.replace(/\\n/g,' ').trim();
                        const dm = text.match(/(\\d{4}\\.\\s*\\d{1,2}\\.\\s*\\d{1,2})\\s*~\\s*(\\d{4}\\.\\s*\\d{1,2}\\.\\s*\\d{1,2})/);
                        if(dm) return {title:text.replace(dm[0],'').substring(0,100).trim(), period:dm[0], image:img.src, link:a?a.href:""};
                        return null;
                    }).filter(x=>x);
                }''')
                for ev in res:
                    all_events.append({"category":"현대카드", "eventName":ev['title'], "period":ev['period'], "link":ev['link'] if ev['link'] and "javascript" not in ev['link'] else "https://www.hyundaicard.com/cpb/ev/CPBEV0101_01.hc", "image":ev['image'], "bgColor":"#000000"})
            except Exception as e: print(f"Hyundai PW error: {e}")
            finally: await browser.close()
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "hyundai_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(HYUNDAI_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] Hyundai crawl finished: {len(all_events)} events saved.")
    except Exception as e: print(f"Hyundai crawl error: {e}")

async def crawl_lotte_bg():
    try:
        print(f"[{datetime.now(seoul_tz)}] Starting Lotte background crawl...")
        from playwright.async_api import async_playwright
        all_events = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")
            page = await ctx.new_page()
            try:
                await page.goto("https://m.lottecard.co.kr/app/LPBNFDA_V100.lc", timeout=90000, wait_until="domcontentloaded")
                await page.wait_for_timeout(10000)
                res = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('li')).map(li => {
                        const img = li.querySelector('img'), a = li.querySelector('a');
                        if(!img) return null;
                        const text = li.innerText.replace(/\\n/g,' ').trim();
                        const dm = text.match(/(\\d{4}\\.\\d{2}\\.\\d{2})\\s*~\\s*(\\d{4}\\.\\d{2}\\.\\d{2})/);
                        if(dm) return {title:text.replace(dm[0],'').substring(0,100).trim(), period:dm[0], image:img.src, link:a?a.href:""};
                        return null;
                    }).filter(x=>x);
                }''')
                for ev in res:
                    all_events.append({"category":"롯데카드", "eventName":ev['title'], "period":ev['period'], "link":ev['link'] if ev['link'] and "javascript" not in ev['link'] else "https://m.lottecard.co.kr/app/LPBNFDA_V100.lc", "image":ev['image'], "bgColor":"#ed1c24"})
            except Exception as e: print(f"Lotte PW error: {e}")
            finally: await browser.close()
        if all_events:
            data = {"last_updated":datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S'), "data":all_events}
            file_path = os.path.join(os.getcwd(), "lotte_data.json")
            with open(file_path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
            if r: r.setex(LOTTE_CACHE_KEY, CACHE_EXPIRE, json.dumps(data))
            print(f"[{datetime.now(seoul_tz)}] Lotte crawl finished: {len(all_events)} events saved.")
    except Exception as e: print(f"Lotte crawl error: {e}")

# --- HTML Handlers ---
@router.get("/card-events", response_class=HTMLResponse)
def card_events(): return HTMLResponse(content=render_template("card_events_main.html"))
@router.get("/card-events/kb", response_class=HTMLResponse)
def kb_card_events(): return HTMLResponse(content=render_template("kb_card_events.html"))
@router.get("/card-events/hana", response_class=HTMLResponse)
def hana_card_events(): return HTMLResponse(content=render_template("hana_card_events.html"))
@router.get("/card-events/shinhan", response_class=HTMLResponse)
def shinhan_card_events(): return HTMLResponse(content=render_template("shinhan_card_events.html"))
@router.get("/card-events/woori", response_class=HTMLResponse)
def woori_card_events(): return HTMLResponse(content=render_template("woori_card_events.html"))
@router.get("/card-events/bc", response_class=HTMLResponse)
def bc_card_events(): return HTMLResponse(content=render_template("bc_card_events.html"))
@router.get("/card-events/samsung", response_class=HTMLResponse)
def samsung_card_events(): return HTMLResponse(content=render_template("samsung_card_events.html"))
@router.get("/card-events/hyundai", response_class=HTMLResponse)
def hyundai_cards_page(): return HTMLResponse(content=render_template("hyundai_card_events.html"))
@router.get("/card-events/lotte", response_class=HTMLResponse)
def lotte_cards_page(): return HTMLResponse(content=render_template("lotte_card_events.html"))
@router.get("/card-events/search", response_class=HTMLResponse)
def card_events_search(): return HTMLResponse(content=render_template("card_events_search.html"))
