import httpx
import os
import json
import zipfile
import io
import xml.etree.ElementTree as ET
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import List, Optional
from datetime import datetime
from shared import r, seoul_tz

router = APIRouter(prefix="/dart", tags=["DART"])

DART_API_KEY = "ff2e6d3bb1647f726c27820722d3553130913037"
CORP_CODE_FILE = "corp_codes.json"

def update_corp_codes():
    """DART에서 고유번호 리스트를 다운로드하여 로컬 JSON으로 저장"""
    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_API_KEY}"
    try:
        response = httpx.get(url, timeout=30.0)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                with z.open("CORPCODE.xml") as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    codes = {}
                    for list_tag in root.findall("list"):
                        corp_name = list_tag.find("corp_name").text
                        corp_code = list_tag.find("corp_code").text
                        stock_code = list_tag.find("stock_code").text
                        # 상장사 위주로 저장 (stock_code가 있는 것)
                        if stock_code and stock_code.strip():
                            codes[corp_name] = {
                                "corp_code": corp_code,
                                "stock_code": stock_code.strip()
                            }
                    
                    with open(CORP_CODE_FILE, "w", encoding="utf-8") as jf:
                        json.dump(codes, jf, ensure_ascii=False, indent=2)
            return codes
    except Exception as e:
        print(f"Error updating corp codes: {e}")
    return {}

def get_corp_codes():
    if os.path.exists(CORP_CODE_FILE):
        with open(CORP_CODE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return update_corp_codes()

@router.get("/search")
async def search_company(q: str = Query(..., min_length=1)):
    codes = get_corp_codes()
    results = []
    for name, info in codes.items():
        if q in name:
            results.append({"name": name, **info})
    return results[:10]

async def fetch_dart_data(corp_code: str, year: str, reprt_code: str):
    """특정 연도/분기의 직원 및 임원 현황 조회"""
    # 직원 현황
    emp_url = f"https://opendart.fss.or.kr/api/empSttus.json?crtfc_key={DART_API_KEY}&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}"
    # 등기임원 현황
    exctv_url = f"https://opendart.fss.or.kr/api/exctvSttus.json?crtfc_key={DART_API_KEY}&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}"
    # 미등기임원 현황
    unrst_url = f"https://opendart.fss.or.kr/api/unrstExctvMendngSttus.json?crtfc_key={DART_API_KEY}&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}"
    
    data = {"employees": 0, "executives": 0}
    
    async with httpx.AsyncClient() as client:
        # 1. 직원 수 계산
        try:
            res_emp = await client.get(emp_url, timeout=10.0)
            if res_emp.status_code == 200:
                emp_json = res_emp.json()
                if emp_json.get("status") == "000":
                    emp_list = emp_json.get("list", [])
                    
                    # 우선순위 1: '성별합계' 또는 '계' 행 찾기
                    totals = []
                    for item in emp_list:
                        sexdstn = str(item.get("sexdstn", ""))
                        fo_bbm = str(item.get("fo_bbm", ""))
                        if "합계" in sexdstn or "합계" in fo_bbm or sexdstn == "계":
                            sm = str(item.get("sm", "0")).replace(",", "")
                            # sm이 '-'인 경우 rgllbr_co + cnttk_co 시도
                            if sm == "-":
                                rgl = str(item.get("rgllbr_co", "0")).replace(",", "")
                                cnt = str(item.get("cnttk_co", "0")).replace(",", "")
                                try: sm = str(int(float(rgl)) + int(float(cnt)))
                                except: sm = "0"
                            totals.append(sm)
                    
                    if totals:
                        data["employees"] = sum(int(float(t)) for t in totals if t not in ["-", "None"])
                    else:
                        # 우선순위 2: 모든 행의 sm 합산 후 중복 제거 (남/여로만 나뉜 경우 등)
                        total_sm = 0
                        for item in emp_list:
                            sm = str(item.get("sm", "0")).replace(",", "")
                            if sm == "-":
                                rgl = str(item.get("rgllbr_co", "0")).replace(",", "")
                                cnt = str(item.get("cnttk_co", "0")).replace(",", "")
                                try: sm = str(int(float(rgl)) + int(float(cnt)))
                                except: sm = "0"
                            try: total_sm += int(float(sm))
                            except: pass
                        # 대략적으로 2로 나눔 (남/여 중복 가정), 만약 너무 작으면 그냥 사용
                        data["employees"] = total_sm // 2 if total_sm > 100 else total_sm
        except: pass

        # 2. 임원 수 계산 (등기 + 미등기)
        total_exctv = 0
        try:
            # 등기임원
            res_exctv = await client.get(exctv_url, timeout=10.0)
            if res_exctv.status_code == 200:
                exctv_json = res_exctv.json()
                if exctv_json.get("status") == "000":
                    total_exctv += len(exctv_json.get("list", []))
        except: pass
        
        try:
            # 미등기임원
            res_unrst = await client.get(unrst_url, timeout=10.0)
            if res_unrst.status_code == 200:
                unrst_json = res_unrst.json()
                if unrst_json.get("status") == "000":
                    for item in unrst_json.get("list", []):
                        nmpr = str(item.get("nmpr", "0")).replace(",", "")
                        try: total_exctv += int(float(nmpr))
                        except: pass
        except: pass
        
        data["executives"] = total_exctv
        
    return data

@router.get("/stats/{corp_code}")
async def get_stats(corp_code: str):
    # 최근 8분기 데이터 조회
    # 2024년 3분기부터 역순으로 (현재 시점 기준)
    now = datetime.now(seoul_tz)
    current_year = now.year
    
    # 보고서 코드: 1분기(11013), 반기(11012), 3분기(11014), 사업보고서(11011)
    reprts = [
        ("2024", "11014", "2024 3Q"),
        ("2024", "11012", "2024 2Q"),
        ("2024", "11013", "2024 1Q"),
        ("2023", "11011", "2023 4Q"),
        ("2023", "11014", "2023 3Q"),
        ("2023", "11012", "2023 2Q"),
        ("2023", "11013", "2023 1Q"),
        ("2022", "11011", "2022 4Q"),
    ]
    
    results = []
    for year, code, label in reprts:
        cache_key = f"dart_stats:{corp_code}:{year}:{code}"
        if r:
            cached = r.get(cache_key)
            if cached:
                results.append({"label": label, **json.loads(cached)})
                continue
        
        data = await fetch_dart_data(corp_code, year, code)
        if r and (data["employees"] > 0 or data["executives"] > 0):
            r.setex(cache_key, 86400 * 30, json.dumps(data)) # 한달 캐시
        
        results.append({"label": label, **data})
    
    return results[::-1] # 시간순 정렬

@router.get("/api/data")
async def get_raw_data(corp_code: str, year: str, reprt_code: str, api_name: str):
    url = f"https://opendart.fss.or.kr/api/{api_name}.json?crtfc_key={DART_API_KEY}&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}"
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "000":
                    return {"status": "success", "list": data.get("list", [])}
                elif data.get("status") == "013":
                    return {"status": "error", "message": "해당 조건의 공시 데이터가 존재하지 않습니다."}
                else:
                    return {"status": "error", "message": data.get("message", "데이터를 불러오는 중 오류가 발생했습니다.")}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "API 요청 중 오류가 발생했습니다."}

@router.get("/", response_class=HTMLResponse)
async def dart_ui():
    path = os.path.join(os.getcwd(), "templates", "dart_main.html")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
