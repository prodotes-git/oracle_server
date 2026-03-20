import httpx
import os
import json
import zipfile
import io
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
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

async def fetch_dividend_data(corp_code: str, year: str, reprt_code: str):
    """특정 연도/분기의 배당 지표 조회"""
    url = f"https://opendart.fss.or.kr/api/alotMatter.json?crtfc_key={DART_API_KEY}&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}"
    res_data = {"dividend_yield": 0.0, "dividend_payout": 0.0, "dividend_per_share": 0}
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "000":
                    for item in data.get("list", []):
                        se = item.get("se", "")
                        thstrm = str(item.get("thstrm", "")).replace(",", "")
                        stock_knd = item.get("stock_knd", "")
                        
                        try: val = float(thstrm) if thstrm != "-" else 0.0
                        except: val = 0.0
                        
                        if "현금배당수익률" in se and "보통주" in stock_knd:
                            res_data["dividend_yield"] = val
                        elif "현금배당성향" in se:
                            res_data["dividend_payout"] = val
                        elif "현금배당금" in se and "보통주" in stock_knd:
                            res_data["dividend_per_share"] = int(val)
        except:
            pass
            
    return res_data

async def fetch_finance_data(corp_code: str, year: str, reprt_code: str):
    """특정 연도/분기의 자산, 부채, 자본 및 매출, 영업이익, 당기순이익 조회"""
    url = f"https://opendart.fss.or.kr/api/fnlttSinglAcnt.json?crtfc_key={DART_API_KEY}&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}"
    res_data = {"revenue": 0, "op_income": 0, "net_income": 0, 
                "cum_revenue": 0, "cum_op_income": 0, "cum_net_income": 0,
                "assets": 0, "liabilities": 0, "equity": 0}
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "000":
                    lst = data.get("list", [])
                    cfs_list = [item for item in lst if item.get("fs_div") == "CFS"]
                    ofs_list = [item for item in lst if item.get("fs_div") == "OFS"]
                    target_list = cfs_list if len(cfs_list) > 0 else ofs_list
                    
                    revenue, op_income, net_income = 0, 0, 0
                    cum_rev, cum_op, cum_net = 0, 0, 0
                    assets, liabilities, equity = 0, 0, 0
                    
                    for item in target_list:
                        acc_nm = item.get("account_nm", "")
                        sj_div = item.get("sj_div", "")
                        
                        amount_str = item.get("thstrm_amount", "0")
                        if not amount_str: continue
                        amount_str = amount_str.replace(",", "")
                        try: amount = int(amount_str)
                        except: amount = 0
                        
                        add_amount_str = item.get("thstrm_add_amount", "")
                        add_amount = amount # 기본적으로 당기금액으로 초기화 (Q1, Q4는 누적=당기)
                        if add_amount_str:
                            try: add_amount = int(add_amount_str.replace(",", ""))
                            except: pass
                        
                        # 재무상태표 항목
                        if sj_div == "BS":
                            if "자산총계" in acc_nm: assets = amount
                            elif "부채총계" in acc_nm: liabilities = amount
                            elif "자본총계" in acc_nm: equity = amount
                        
                        # 손익계산서 항목
                        if sj_div in ["IS", "CIS"]:
                            if acc_nm in ["매출액", "수익(매출액)"]:
                                revenue = amount
                                cum_rev = add_amount
                            elif acc_nm in ["영업이익", "영업이익(손실)"]:
                                op_income = amount
                                cum_op = add_amount
                            elif acc_nm in ["당기순이익", "당기순이익(손실)"]:
                                net_income = amount
                                cum_net = add_amount
                                
                    res_data["revenue"] = revenue
                    res_data["op_income"] = op_income
                    res_data["net_income"] = net_income
                    res_data["cum_revenue"] = cum_rev
                    res_data["cum_op_income"] = cum_op
                    res_data["cum_net_income"] = cum_net
                    res_data["assets"] = assets
                    res_data["liabilities"] = liabilities
                    res_data["equity"] = equity
        except:
            pass
            
    return res_data

async def find_rcept_no(client, corp_code: str, year: str, reprt_code: str):
    """list.json API로 정기보고서의 rcept_no 조회"""
    detail_map = {"11011": "A001", "11012": "A002", "11013": "A003", "11014": "A003"}
    pblntf_detail_ty = detail_map.get(reprt_code, "A001")
    bgn_de = f"{year}0101"
    end_de = f"{int(year)+1}1231"
    
    url = (f"https://opendart.fss.or.kr/api/list.json?"
           f"crtfc_key={DART_API_KEY}&corp_code={corp_code}"
           f"&bgn_de={bgn_de}&end_de={end_de}"
           f"&pblntf_ty=A&pblntf_detail_ty={pblntf_detail_ty}"
           f"&page_count=30")
    
    try:
        res = await client.get(url, timeout=15.0)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "000":
                lst = data.get("list", [])
                reprt_nm_map = {"11011": "사업보고서", "11012": "반기보고서", "11013": "분기보고서", "11014": "분기보고서"}
                target_nm = reprt_nm_map.get(reprt_code, "사업보고서")
                
                for item in lst:
                    report_nm = item.get("report_nm", "")
                    if reprt_code == "11013" and "1분기" not in report_nm: continue
                    if reprt_code == "11014" and "3분기" not in report_nm: continue
                    if target_nm in report_nm or report_nm.startswith("["): return item.get("rcept_no")
                
                if lst: return lst[0].get("rcept_no")
    except Exception as e:
        print(f"find_rcept_no error: {e}")
    return None

async def download_and_parse_order_backlog(client, rcept_no: str):
    """보고서 원문 ZIP 다운로드 후 수주상황 테이블 파싱"""
    url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={DART_API_KEY}&rcept_no={rcept_no}"
    try:
        res = await client.get(url, timeout=30.0)
        if res.status_code != 200: return []
        
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            for fname in z.namelist():
                if not fname.endswith(('.xml', '.html', '.htm')): continue
                with z.open(fname) as f:
                    content = f.read()
                    try: text = content.decode('utf-8')
                    except:
                        try: text = content.decode('euc-kr')
                        except: text = content.decode('cp949', errors='ignore')
                    
                    if '수주' not in text: continue
                    tables = parse_order_tables(text)
                    if tables: return tables
    except Exception as e:
        print(f"download_and_parse error: {e}")
    return []

def parse_order_tables(html_text: str):
    """HTML에서 수주상황 관련 테이블 파싱"""
    soup = BeautifulSoup(html_text, 'lxml')
    results = []
    order_keywords = ['수주상황', '수주현황', '수주 상황', '수주 현황', '매출 및 수주', '매출및수주']
    target_tables = []
    
    for keyword in order_keywords:
        for tag in soup.find_all(string=re.compile(keyword)):
            parent = tag.parent
            for sibling in parent.find_all_next('table'):
                if sibling not in target_tables: target_tables.append(sibling)
                if len(target_tables) >= 5: break
            if target_tables: break
        if target_tables: break
    
    if not target_tables: return []
    
    for table in target_tables:
        rows = table.find_all('tr')
        if len(rows) < 2: continue
        
        header_row, header_idx = None, 0
        for i, row in enumerate(rows):
            cells = row.find_all(['th', 'td'])
            cell_texts = [c.get_text(strip=True) for c in cells]
            header_text = ' '.join(cell_texts)
            if any(kw in header_text for kw in ['수주잔고', '잔고', '수주총액', '품목', '제품', '수주일자', '납기']):
                header_row, header_idx = cell_texts, i
                break
        
        if not header_row:
            cells = rows[0].find_all(['th', 'td'])
            header_row, header_idx = [c.get_text(strip=True) for c in cells], 0
        
        if len(header_row) < 2: continue
        
        for row in rows[header_idx + 1:]:
            cells = row.find_all(['td', 'th'])
            cell_texts = [c.get_text(strip=True) for c in cells]
            if len(cell_texts) < 2: continue
            if all(not t or t == '-' for t in cell_texts): continue
            
            row_data = {}
            for j, header in enumerate(header_row):
                if j < len(cell_texts): row_data[header] = cell_texts[j]
            
            if row_data: results.append(row_data)
        
        if results: break
    
    return results

def parse_amount_str(val_str):
    if not val_str: return 0
    cleaned = re.sub(r'[^\d.-]', '', str(val_str))
    try:
        num = float(cleaned)
        return num if not math.isnan(num) else 0
    except: return 0

import math

async def fetch_order_backlog_data(corp_code: str, year: str, reprt_code: str):
    """원문 파싱으로 정확한 수주총액, 수주잔고 합계를 추출"""
    res_data = {"order_total": 0, "order_backlog": 0, "order_delivered": 0}
    
    async with httpx.AsyncClient() as client:
        rcept_no = await find_rcept_no(client, corp_code, year, reprt_code)
        if not rcept_no: return res_data
        
        tables = await download_and_parse_order_backlog(client, rcept_no)
        if not tables: return res_data
        
        # 합계 구하기 로직 (요약 행 무시하고 전부 합산, 또는 합계행만 찾기)
        # 여기서는 가장 단순하게 전체 row의 액수를 합산하거나 합계 행만 씁니다.
        # 기업마다 "합계" 행이 있거나 없는 경우가 있어서 통계 오류를 막기 위해
        # 항목들의 총 합이 "합계"와 같은지 체크하는 것은 복잡하므로,
        # '합계' 또는 '총'이 들어간 row가 있으면 그 row만 사용,
        # 없으면 전체 row 값을 모두 합쳐서 산출.
        
        has_total_row = any(any("합계" in str(val) or "총계" in str(val) for val in row.values()) for row in tables)
        
        backlog_sum, total_sum, delivered_sum = 0, 0, 0
        
        for row in tables:
            is_total_row = any("합계" in str(val) or "총계" in str(val) for val in row.values())
            
            # 합계 행이 존재한다면, 합계 행 이외의 데이터는 버림
            if has_total_row and not is_total_row:
                continue
                
            for k, v in row.items():
                kl = k.lower()
                amount = parse_amount_str(v)
                # 실제 화폐단위(백만, 천원 등) 스케일링은 헤더에 표기된 경우가 많으나,
                # 기본적으로 수치가 재무제표 단위(원)와 비슷하게 맞추기 위해 1,000,000 단위 등을 곱해야 할 수 있습니다.
                # 그러나 DART 공시 표마다 단위가 다르므로, 원시 숫자의 절대합만 반영 (프론트에서 축 스케일로 표시)
                if '잔고' in kl or '잔액' in kl:
                    backlog_sum += amount
                if '수주총액' in kl or '총액' in kl:
                    total_sum += amount
                if '기납품액' in kl or '납품' in kl:
                    delivered_sum += amount
        
        # 파싱된 숫자(보통 표의 단위가 '백만원' 혹은 '천원')를 재무제표 수준(보통 '원')으로 대략 보정 (숫자가 너무 작다면 백만 곱하기 등)
        # 그러나 DART 수주표는 보통 백만원 단위가 많음을 고려하여,
        # 파싱된 금액이 10억 미만(ex: 100,000 단위)이라면 1,000,000원을 곱해주는 식으로 보정할 수도 있으나,
        # 일단은 그대로 합산하여 리턴합니다.
        # 수주잔고는 계약자산/부채를 대체하는 것이므로 금액이 작다면 (단위: 백만원) 1,000,000 배 곱해줍니다.
        if backlog_sum > 0 and backlog_sum < 10000000:
            backlog_sum *= 1000000
            total_sum *= 1000000
            delivered_sum *= 1000000
            
        res_data["order_backlog"] = backlog_sum
        res_data["order_total"] = total_sum
        res_data["order_delivered"] = delivered_sum
        
    return res_data


@router.get("/stats/{corp_code}")
async def get_stats(corp_code: str):
    # 최근 8분기 데이터 조회
    # 2024년 3분기부터 역순으로 (현재 시점 기준)
    now = datetime.now(seoul_tz)
    current_year = now.year
    
    # 보고서 코드: 1분기(11013), 반기(11012), 3분기(11014), 사업보고서(11011)
    # 최근 5~6년(현재 연도 포함) 분기 데이터 동적 생성
    reprts = []
    for y in range(current_year, current_year - 6, -1):
        year_str = str(y)
        reprts.extend([
            (year_str, "11011", f"{year_str} 4Q"),
            (year_str, "11014", f"{year_str} 3Q"),
            (year_str, "11012", f"{year_str} 2Q"),
            (year_str, "11013", f"{year_str} 1Q"),
        ])
    
    # 비동기 데이터 묶음 가져오기
    import asyncio
    
    raw_results = []
    
    for year, code, label in reprts:
        cache_key = f"dart_stats_v7:{corp_code}:{year}:{code}"
        cached = r.get(cache_key) if r else None
        
        if cached:
            raw_results.append({"label": label, "year": year, "code": code, **json.loads(cached)})
        else:
            emp_task = fetch_dart_data(corp_code, year, code)
            fin_task = fetch_finance_data(corp_code, year, code)
            div_task = fetch_dividend_data(corp_code, year, code)
            ob_task = fetch_order_backlog_data(corp_code, year, code)
            
            emp_data, fin_data, div_data, ob_data = await asyncio.gather(emp_task, fin_task, div_task, ob_task)
            combined = {**emp_data, **fin_data, **div_data, **ob_data}
            
            if r and (combined["employees"] > 0 or combined["revenue"] > 0 or combined["assets"] > 0):
                r.setex(cache_key, 86400 * 30, json.dumps(combined)) # 한달 캐시
                
            raw_results.append({"label": label, "year": year, "code": code, **combined})
            
    # 4분기 실적(11011) 단독 분리 처리: (4Q = 1년간 누적결산 - 3분기 누적)
    # raw_results는 순서대로 들어있으므로 year로 접근하기 편하게 mapping을 만듬
    # 3분기(11014)의 cum_revenue (누적액)을 4분기(11011) 총액에서 뺌
    
    by_year_code = { f"{rv['year']}_{rv['code']}": rv for rv in raw_results }
    
    results = []
    for rv in raw_results:
        # 4분기인 경우, 3분기(11014) 누적 데이터가 조회 가능한지 확인 후 차감
        if rv["code"] == "11011":
            q3_key = f"{rv['year']}_11014"
            if q3_key in by_year_code:
                q3_data = by_year_code[q3_key]
                if rv["revenue"] > 0 and q3_data["cum_revenue"] > 0:
                    rv["revenue"] = rv["revenue"] - q3_data["cum_revenue"]
                    rv["op_income"] = rv["op_income"] - q3_data["cum_op_income"]
                    rv["net_income"] = rv["net_income"] - q3_data["cum_net_income"]
        
        results.append(rv)

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
