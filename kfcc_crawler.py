import asyncio
import httpx
from bs4 import BeautifulSoup
import re

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
    "Content-Type": "application/x-www-form-urlencoded"
}

# 12개월 금리 파싱
def parse_rate(val):
    try:
        if not val or "연" not in val: return None
        return val.replace("연", "").replace("%", "").strip()
    except:
        return None

# 상품별 금리 파싱
def parse_html(html, target_products=["MG더뱅킹정기예금", "MG더뱅킹정기적금", "MG더뱅킹자유적금"]):
    soup = BeautifulSoup(html, "lxml")
    base_date = soup.select_one(".base-date")
    base_date_txt = base_date.text.strip() if base_date else ""
    # 조회기준일(2023/01/01) -> 2023/01/01
    date_match = re.search(r"\d{4}/\d{2}/\d{2}", base_date_txt)
    base_date_v = date_match.group(0) if date_match else None

    result = {}
    
    tables = soup.select(".tblWrap")
    for tbl in tables:
        title_elem = tbl.select_one(".tbl-tit")
        if not title_elem: continue
        title = title_elem.text.strip()
        
        if title in target_products:
            # 12개월 금리 찾기
            rows = tbl.select("#divTmp1 tbody tr")
            for row in rows:
                cols = row.select("td")
                if len(cols) >= 2:
                    key = cols[-2].text.strip() # 기간 (12개월 이상)
                    val = cols[-1].text.strip() # 금리 (연X.XX%)
                    
                    if "12" in key and "월" in key:
                        result[title] = parse_rate(val)
                        break
    
    return base_date_v, result

async def fetch_region_banks(client, r1, r2):
    url = f"https://www.kfcc.co.kr/map/list.do?r1={r1}&r2={r2}"
    if r1 == "세종": # 세종 예외처리
        url = f"https://www.kfcc.co.kr/map/list.do?r1={r1}&r2="
        
    try:
        resp = await client.get(url, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("tr")
        banks = []
        for row in rows:
            # id가 없거나 onclick이 없는 row는 건너뜀
            if not row.has_attr("onclick"): continue
            
            # 파싱 로직: onclick="parent.mapGo('0101', '3333', '...')"
            # 또는 td span title="새마을금고코드"
            td = row.select_one("td")
            if not td: continue
            
            data = {}
            spans = td.select("span")
            for span in spans:
                if span.has_attr("title"):
                    data[span["title"]] = span.text.strip()
            
            if "새마을금고코드" in data:
                banks.append({
                    "gmgoCd": data["새마을금고코드"],
                    "gmgoNm": data.get("새마을금고명", ""),
                    "divCd": data.get("지점구분코드", ""), # 001:본점
                    "r1": r1,
                    "r2": r2,
                    "location": f"{r1} {r2}"
                })
        return banks
    except Exception as e:
        print(f"Error fetching region {r1} {r2}: {e}")
        return []

async def fetch_bank_rates(client, bank):
    gmgoCd = bank["gmgoCd"]
    res_data = {
        "gmgoCd": gmgoCd,
        "gmgoNm": bank["gmgoNm"],
        "location": bank["location"],
        "MG더뱅킹정기예금": None,
        "MG더뱅킹정기적금": None,
        "MG더뱅킹자유적금": None,
        "기준일": None
    }
    
    # 13: 예탁금, 14: 적금
    # 3번 재시도 로직은 생략하고 1번 시도
    try:
        # 예탁금
        url_dep = f"https://www.kfcc.co.kr/map/goods_19.do?OPEN_TRMID={gmgoCd}&gubuncode=13"
        resp_dep = await client.get(url_dep, headers=HEADERS)
        date, rates = parse_html(resp_dep.text)
        if date: res_data["기준일"] = date
        if "MG더뱅킹정기예금" in rates: res_data["MG더뱅킹정기예금"] = rates["MG더뱅킹정기예금"]

        # 적금
        url_sav = f"https://www.kfcc.co.kr/map/goods_19.do?OPEN_TRMID={gmgoCd}&gubuncode=14"
        resp_sav = await client.get(url_sav, headers=HEADERS)
        _, rates_sav = parse_html(resp_sav.text)
        if "MG더뱅킹정기적금" in rates_sav: res_data["MG더뱅킹정기적금"] = rates_sav["MG더뱅킹정기적금"]
        if "MG더뱅킹자유적금" in rates_sav: res_data["MG더뱅킹자유적금"] = rates_sav["MG더뱅킹자유적금"]
        
        return res_data
    except Exception as e:
        # print(f"Error fetching rates for {bank['gmgoNm']}: {e}")
        return res_data

async def run_crawler():
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. 모든 지역의 금고 목록 수집
        print("Fetching bank lists...")
        bank_tasks = []
        for region in ALL_REGIONS:
            r1 = region[0]
            sub_regions = region[1:]
            for r2 in sub_regions:
                bank_tasks.append(fetch_region_banks(client, r1, r2))
        
        # 동시성 제한을 두어 요청
        # (너무 빠르면 차단될 수 있으므로 청크 단위로 진행하거나 세마포어 사용)
        semaphore = asyncio.Semaphore(10) # 10개씩 동시 요청
        
        async def fetch_with_sem(coro):
            async with semaphore:
                return await coro

        all_banks_nested = await asyncio.gather(*(fetch_with_sem(t) for t in bank_tasks))
        all_banks = [b for sublist in all_banks_nested for b in sublist]
        
        # 중복 제거 (본점/지점 등이 겹칠 수 있음)
        unique_banks = {b['gmgoCd']: b for b in all_banks}.values()
        print(f"Total unique banks found: {len(unique_banks)}")

        # 2. 각 금고의 금리 수집
        print("Fetching interest rates...")
        rate_tasks = [fetch_bank_rates(client, bank) for bank in unique_banks]
        
        # 금리 조회도 세마포어 적용 (더 보수적으로)
        rate_sem = asyncio.Semaphore(20)
        async def fetch_rate_with_sem(coro):
            async with rate_sem:
                 # 약간의 딜레이 추가
                await asyncio.sleep(0.05)
                return await coro
                
        results = []
        total = len(rate_tasks)
        for i, coro in enumerate(asyncio.as_completed([fetch_rate_with_sem(t) for t in rate_tasks])):
            res = await coro
            results.append(res)
            if i % 100 == 0:
                print(f"Progress: {i}/{total}")

        # 3. 데이터 포맷팅 (report_mat.json 형식)
        # [header, [row1], [row2]...]
        header = ["gmgoCd", "gmgoNm", "location", "MG더뱅킹정기예금", "MG더뱅킹정기적금", "MG더뱅킹자유적금", "기준일"]
        final_data = [header]
        
        for r in results:
            row = [
                r["gmgoCd"],
                r["gmgoNm"],
                r["location"],
                r["MG더뱅킹정기예금"],
                r["MG더뱅킹정기적금"],
                r["MG더뱅킹자유적금"],
                r["기준일"]
            ]
            final_data.append(row)
            
        return final_data

if __name__ == "__main__":
    data = asyncio.run(run_crawler())
    print(f"Collected {len(data)-1} records.")
