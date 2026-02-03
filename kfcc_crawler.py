import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import json

# KFCC 지역 데이터 (Regions)
ALL_REGIONS = [
    ["서울", "도봉구", "마포구", "관악구", "강북구", "용산구", "서초구", "노원구", "성동구", "강남구", "성북구", "광진구", "송파구", "은평구", "강서구", "강동구", "종로구", "양천구", "중랑구", "영등포구", "서대문구", "구로구", "동대문구", "동작구", "중구", "금천구"],
    ["인천", "강화군", "서구", "동구", "중구", "미추홀구", "연수구", "계양구", "부평구", "남동구"],
    ["경기", "김포시", "파주시", "연천군", "고양시", "양주시", "동두천", "포천시", "의정부", "남양주시", "구리시", "가평군", "하남시", "부천시", "광명시", "시흥시", "안산시", "안양시", "과천시", "군포시", "의왕시", "성남시", "광주시", "양평군", "화성시", "수원시", "오산시", "용인시", "이천시", "여주시", "평택시", "안성시"],
    ["강원", "철원군", "화천군", "양구군", "춘천시", "인제군", "고성군", "속초시", "양양군", "홍천군", "강릉시", "원주시", "횡성군", "평창군", "영월군", "정선군", "동해시", "삼척시", "태백시"],
    ["충남", "태안군", "서산시", "당진시", "홍성군", "예산군", "아산시", "천안시", "보령시", "청양군", "공주시", "연기군", "서천군", "부여군", "논산시", "금산군"],
    ["충북", "청주시", "진천군", "음성군", "충주시", "제천시", "청원군", "괴산군", "단양군", "보은군", "옥천군", "영동군", "증평군"],
    ["대전", "유성구", "대덕구", "서구", "중구", "동구"],
    ["경북", "문경시", "예천군", "영주시", "봉화군", "울진군", "상주시", "의성군", "안동시", "영양군", "김천시", "구미시", "군위군", "청송군", "영덕군", "성주군", "칠곡군", "영천시", "포항시", "고령군", "경산시", "경주시", "청도군", "울릉군"],
    ["경남", "함양군", "거창군", "산청군", "합천군", "하동군", "진주시", "의령군", "함안군", "창녕군", "남해군", "사천시", "고성군", "마산시", "창원시", "밀양시", "통영시", "거제시", "진해시", "김해시", "양산시"],
    ["대구", "서구", "북구", "동구", "달서구", "중구", "남구", "수성구", "달성군"],
    ["부산", "강서구", "북구", "금정구", "기장군", "사상구", "부산진구", "연제구", "동래구", "사하구", "서구", "중구", "동구", "남구", "수영구", "해운대구", "영도구"],
    ["울산", "울주군", "북구", "중구", "남구", "동구"],
    ["전북", "군산시", "익산시", "부안군", "김제시", "완주군", "전주시", "고창군", "정읍시", "순창군", "임실군", "진안군", "무주군", "남원시", "장수군"],
    ["전남", "영광군", "장성군", "담양군", "함평군", "신안군", "무안군", "나주시", "화순군", "곡성군", "구례군", "목포시", "영암군", "진도군", "해남군", "강진군", "장흥군", "보성군", "순천시", "완도군", "고흥군", "여수시", "광양시"],
    ["광주", "광산구", "북구", "서구", "남구", "동구"],
    ["제주", "제주시", "서귀포시"],
    ["세종", "세종시"]
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# 수집 대상 상품 (MG더뱅킹 3종)
TARGET_PRODUCTS = ["MG더뱅킹정기예금", "MG더뱅킹정기적금", "MG더뱅킹자유적금"]

def parse_rate(val):
    try:
        match = re.search(r"([\d\.]+)", val)
        if match: return match.group(1)
        return None
    except: return None

def cleanup_title(title):
    return re.sub(r"\s+", "", title)

def parse_html(html):
    soup = BeautifulSoup(html, "lxml")
    
    base_date = ""
    date_elem = soup.select_one(".base-date")
    if date_elem:
        m = re.search(r"\d{4}/\d{2}/\d{2}", date_elem.text)
        if m: base_date = m.group(0)

    # 12개월 금리만 추출
    rates = {}
    
    sections = soup.select("#divTmp1")
    for sec in sections:
        tit_elem = sec.select_one(".tbl-tit")
        if not tit_elem: continue
        title = cleanup_title(tit_elem.text.strip())
        
        # 지정된 3가지 상품만 수집
        if title in TARGET_PRODUCTS:
            rows = sec.select("tbody tr")
            for row in rows:
                cols = row.select("td")
                if len(cols) >= 2:
                    period_txt = cols[-2].text.strip()
                    rate_txt = cols[-1].text.strip()
                    
                    # "12개월" 키워드 정밀 매칭
                    if "12" in period_txt and "개월" in period_txt:
                        rate = parse_rate(rate_txt)
                        if rate:
                            rates[title] = rate
                            break # 해당 상품의 12개월 금리 찾았으면 다음 상품으로
                            
    return base_date, rates

async def fetch_region_banks(client, r1, r2):
    url = f"https://www.kfcc.co.kr/map/list.do?r1={r1}&r2={r2}"
    if r1 == "세종": url = f"https://www.kfcc.co.kr/map/list.do?r1={r1}&r2="
    
    try:
        resp = await client.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200: return []
        
        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("tr")
        banks = []
        for row in rows:
            td = row.select_one("td")
            if not td: continue
            meta = {}
            for s in td.select("span"):
                if s.has_attr("title"): meta[s["title"]] = s.text.strip()
            
            cd = meta.get("gmgoCd") or meta.get("새마을금고코드")
            nm = meta.get("gmgoNm") or meta.get("새마을금고명")
            if cd and nm:
                banks.append({
                    "gmgoCd": cd,
                    "gmgoNm": nm,
                    "r1": r1,
                    "r2": r2,
                    "addr": meta.get("addr") or f"{r1} {r2}"
                })
        return banks
    except Exception as e:
        return []

async def fetch_bank_rates(client, bank, semaphore):
    async with semaphore:
        gmgoCd = bank["gmgoCd"]
        data = {
            "gmgoCd": gmgoCd,
            "gmgoNm": bank["gmgoNm"],
            "location": bank["addr"],
            "rates": {},
            "기준일": None
        }
        
        try:
            # 1. 거치식예탁금 (gubuncode 13) - MG더뱅킹정기예금 포함
            res_dep = await client.get(f"https://www.kfcc.co.kr/map/goods_19.do?OPEN_TRMID={gmgoCd}&gubuncode=13", headers=HEADERS)
            if res_dep.status_code == 200:
                date, r_dep = parse_html(res_dep.text)
                if date: data["기준일"] = date
                data["rates"].update(r_dep)
            
            # 2. 적립식예탁금 (gubuncode 14) - MG더뱅킹정기적금/자유적금 포함
            res_sav = await client.get(f"https://www.kfcc.co.kr/map/goods_19.do?OPEN_TRMID={gmgoCd}&gubuncode=14", headers=HEADERS)
            if res_sav.status_code == 200:
                _, r_sav = parse_html(res_sav.text)
                data["rates"].update(r_sav)
                
            return data
        except:
            return data

async def run_crawler():
    print("[KFCC] Starting 12-month targeted crawl...")
    async with httpx.AsyncClient(timeout=20, verify=False) as client:
        # 1. 금고 목록 수집
        region_tasks = []
        for reg in ALL_REGIONS:
            r1 = reg[0]
            for r2 in reg[1:]: region_tasks.append(fetch_region_banks(client, r1, r2))
        
        region_results = await asyncio.gather(*region_tasks)
        all_banks = []
        for res in region_results: all_banks.extend(res)
        
        unique_banks = {b['gmgoCd']: b for b in all_banks}.values()
        print(f"[KFCC] Found {len(unique_banks)} unique banks.")
        
        # 2. 금리 정보 수집
        rate_semaphore = asyncio.Semaphore(15) # 병렬성 약간 조절 (메모리 안정성)
        results = []
        unique_banks_list = list(unique_banks)
        total = len(unique_banks_list)
        
        # 전체 태스크를 한꺼번에 만들지 않고 배치 단위로 실행하여 메모리 절약
        batch_size = 100
        for i in range(0, total, batch_size):
            batch = unique_banks_list[i : i + batch_size]
            rate_tasks = [fetch_bank_rates(client, bank, rate_semaphore) for bank in batch]
            
            batch_results = await asyncio.gather(*rate_tasks)
            for res in batch_results:
                if res and res.get("rates"):
                    results.append(res)
            
            # 진행 상황 출력
            print(f"[KFCC] Progress: {min(i + batch_size, total)}/{total} banks processed. (Found {len(results)} valid rates)")
        
        print(f"[KFCC] Crawl complete. {len(results)} banks with 12-month targeted rates collected.")
        return results

if __name__ == "__main__":
    from datetime import datetime
    import pytz
    seoul_tz = pytz.timezone('Asia/Seoul')
    
    loop = asyncio.get_event_loop()
    data = loop.run_until_complete(run_crawler())
    
    current_time = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
    save_data = {"last_updated": current_time, "data": data}
    
    with open("kfcc_data.json", "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(data)} items to kfcc_data.json")
