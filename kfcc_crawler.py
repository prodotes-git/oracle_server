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

# 수집 대상 기간 (개월 수)
TARGET_DURATIONS = [1, 3, 6, 12, 13, 24, 36]

def parse_rate(val):
    try:
        # 숫자 형식만 추출 (예: '연5.20%' -> '5.20')
        match = re.search(r"([\d\.]+)", val)
        if match: return match.group(1)
        return None
    except: return None

def cleanup_title(title):
    # 공백 및 불필요한 문자 제거
    return re.sub(r"\s+", "", title)

def parse_html(html):
    soup = BeautifulSoup(html, "lxml")
    
    # 기준일 추출
    base_date = ""
    date_elem = soup.select_one(".base-date")
    if date_elem:
        m = re.search(r"\d{4}/\d{2}/\d{2}", date_elem.text)
        if m: base_date = m.group(0)

    # 상품명별 금리 저장
    product_rates = {}
    
    # #divTmp1 섹션 (기본이율 테이블)
    sections = soup.select("#divTmp1")
    for sec in sections:
        tit_elem = sec.select_one(".tbl-tit")
        if not tit_elem: continue
        raw_title = tit_elem.text.strip()
        title = cleanup_title(raw_title)
        
        if title not in product_rates:
            product_rates[title] = {}
        
        rows = sec.select("tbody tr")
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 2:
                period_txt = cols[-2].text.strip()
                rate_txt = cols[-1].text.strip()
                
                # 기간 추출 (숫자만)
                period_match = re.search(r"(\d+)개월", period_txt)
                if period_match:
                    months = int(period_match.group(1))
                    if months in TARGET_DURATIONS:
                        rate = parse_rate(rate_txt)
                        if rate:
                            # 동일 상품 내 기간별 금리 저장
                            product_rates[title][f"{months}개월"] = rate
                            
    return base_date, product_rates

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
        print(f"Error fetching banks for {r1} {r2}: {e}")
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
            # 1. 거치식예탁금 (gubuncode 13)
            res_dep = await client.get(f"https://www.kfcc.co.kr/map/goods_19.do?OPEN_TRMID={gmgoCd}&gubuncode=13", headers=HEADERS)
            if res_dep.status_code == 200:
                date, r_dep = parse_html(res_dep.text)
                if date: data["기준일"] = date
                data["rates"].update(r_dep)
            
            # 2. 적립식예탁금 (gubuncode 14)
            res_sav = await client.get(f"https://www.kfcc.co.kr/map/goods_19.do?OPEN_TRMID={gmgoCd}&gubuncode=14", headers=HEADERS)
            if res_sav.status_code == 200:
                _, r_sav = parse_html(res_sav.text)
                data["rates"].update(r_sav)
                
            return data
        except:
            return data

async def run_crawler():
    print("[KFCC] Starting precision crawl...")
    async with httpx.AsyncClient(timeout=20, verify=False) as client:
        # 1. 금고 목록 수집
        print("[KFCC] Phase 1: Fetching bank list...")
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
        print("[KFCC] Phase 2: Fetching rates...")
        rate_semaphore = asyncio.Semaphore(25)
        rate_tasks = [fetch_bank_rates(client, bank, rate_semaphore) for bank in unique_banks]
        
        results = []
        total = len(rate_tasks)
        for i, coro in enumerate(asyncio.as_completed(rate_tasks)):
            res = await coro
            if res["rates"]:
                results.append(res)
            
            if (i+1) % 50 == 0 or (i+1) == total:
                print(f"[KFCC] Progress: {i+1}/{total} banks processed.")
        
        print(f"[KFCC] Crawl complete. {len(results)} banks collected.")
        return results

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    data = loop.run_until_complete(run_crawler())
    with open("kfcc_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
