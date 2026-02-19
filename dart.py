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

@router.get("/", response_class=HTMLResponse)
async def dart_ui():
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DART 임직원 현황 분석 - inbestlab</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            :root {
                --bg: #0b0e14;
                --card-bg: #161b22;
                --accent: #2f81f7;
                --text: #adbac7;
                --title: #ffffff;
                --border: #30363d;
            }
            body {
                background-color: var(--bg);
                color: var(--text);
                font-family: 'Outfit', 'Noto Sans KR', sans-serif;
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                align-items: center;
                min-height: 100vh;
            }
            .container {
                width: 100%;
                max-width: 1000px;
                padding: 40px 20px;
                box-sizing: border-box;
            }
            header {
                text-align: center;
                margin-bottom: 40px;
            }
            h1 {
                font-size: 42px;
                color: var(--title);
                margin-bottom: 10px;
                background: linear-gradient(90deg, #58a6ff, #bc8cff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .search-box {
                position: relative;
                margin-bottom: 30px;
            }
            input {
                width: 100%;
                padding: 15px 25px;
                border-radius: 30px;
                border: 1px solid var(--border);
                background: var(--card-bg);
                color: white;
                font-size: 18px;
                outline: none;
                transition: all 0.3s;
            }
            input:focus {
                border-color: var(--accent);
                box-shadow: 0 0 15px rgba(47, 129, 247, 0.3);
            }
            .suggestions {
                position: absolute;
                top: 60px;
                width: 100%;
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 15px;
                z-index: 100;
                display: none;
                overflow: hidden;
            }
            .suggestion-item {
                padding: 12px 20px;
                cursor: pointer;
                border-bottom: 1px solid var(--border);
            }
            .suggestion-item:hover {
                background: #21262d;
            }
            .chart-container {
                background: var(--card-bg);
                border-radius: 20px;
                padding: 30px;
                border: 1px solid var(--border);
                margin-bottom: 30px;
                display: none;
            }
            .summary-cards {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
                display: none;
            }
            .stat-card {
                background: var(--card-bg);
                padding: 20px;
                border-radius: 15px;
                border: 1px solid var(--border);
                text-align: center;
            }
            .stat-label { font-size: 14px; color: var(--text); }
            .stat-value { font-size: 32px; font-weight: 700; color: var(--title); margin: 5px 0; }
            .loading {
                display: none;
                text-align: center;
                margin-top: 20px;
            }
            .spinner {
                border: 4px solid rgba(255, 255, 255, 0.1);
                width: 36px;
                height: 36px;
                border-radius: 50%;
                border-left-color: var(--accent);
                animation: spin 1s linear infinite;
                display: inline-block;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            nav {
                width: 100%;
                padding: 20px;
                background: rgba(11, 14, 20, 0.8);
                backdrop-filter: blur(10px);
                position: sticky;
                top: 0;
                z-index: 1000;
                border-bottom: 1px solid var(--border);
                display: flex;
                justify-content: flex-start;
            }
            .back-link {
                color: var(--accent);
                text-decoration: none;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 8px;
            }
        </style>
    </head>
    <body>
        <nav>
            <a href="/" class="back-link">← 대시보드</a>
        </nav>
        <div class="container">
            <header>
                <h1>Corporate Insight</h1>
                <p>국내 기업의 임직원 현황 및 전적 추이를 분석합니다.</p>
            </header>

            <div class="search-box">
                <input type="text" id="searchInput" placeholder="기업명을 입력하세요 (예: 삼성전자)" autocomplete="off">
                <div class="suggestions" id="suggestions"></div>
            </div>

            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>데이터를 분석 중입니다...</p>
            </div>

            <div class="summary-cards" id="summaryCards">
                <div class="stat-card">
                    <div class="stat-label">최근 총 직원 수</div>
                    <div class="stat-value" id="empValue">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">최근 총 임원 수</div>
                    <div class="stat-value" id="exctvValue">-</div>
                </div>
            </div>

            <div class="chart-container" id="chartContainer">
                <canvas id="dartChart"></canvas>
            </div>
        </div>

        <script>
            const searchInput = document.getElementById('searchInput');
            const suggestions = document.getElementById('suggestions');
            const loading = document.getElementById('loading');
            const summaryCards = document.getElementById('summaryCards');
            const chartContainer = document.getElementById('chartContainer');
            let chart = null;

            searchInput.addEventListener('input', async (e) => {
                const q = e.target.value;
                if (q.length < 2) {
                    suggestions.style.display = 'none';
                    return;
                }

                const res = await fetch(`/dart/search?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                
                if (data.length > 0) {
                    suggestions.innerHTML = data.map(item => `
                        <div class="suggestion-item" onclick="selectCompany('${item.corp_code}', '${item.name}')">
                            ${item.name} <span style="font-size:12px; color:#666;">(${item.stock_code})</span>
                        </div>
                    `).join('');
                    suggestions.style.display = 'block';
                } else {
                    suggestions.style.display = 'none';
                }
            });

            async function selectCompany(corpCode, name) {
                searchInput.value = name;
                suggestions.style.display = 'none';
                loading.style.display = 'block';
                summaryCards.style.display = 'none';
                chartContainer.style.display = 'none';

                const res = await fetch(`/dart/stats/${corpCode}`);
                const data = await res.json();
                
                loading.style.display = 'none';
                renderDashboard(data);
            }

            function renderDashboard(data) {
                summaryCards.style.display = 'grid';
                chartContainer.style.display = 'block';

                const last = data[data.length - 1];
                document.getElementById('empValue').innerText = last.employees.toLocaleString();
                document.getElementById('exctvValue').innerText = last.executives.toLocaleString();

                const ctx = document.getElementById('dartChart').getContext('2d');
                
                if (chart) chart.destroy();

                chart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.map(d => d.label),
                        datasets: [
                            {
                                label: '직원 수',
                                data: data.map(d => d.employees),
                                borderColor: '#2f81f7',
                                backgroundColor: 'rgba(47, 129, 247, 0.1)',
                                tension: 0.3,
                                fill: true,
                                yAxisID: 'y'
                            },
                            {
                                label: '임원 수',
                                data: data.map(d => d.executives),
                                borderColor: '#bc8cff',
                                backgroundColor: 'rgba(188, 140, 255, 0.1)',
                                tension: 0.3,
                                fill: true,
                                yAxisID: 'y1'
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        interaction: {
                            mode: 'index',
                            intersect: false,
                        },
                        plugins: {
                            legend: {
                                labels: { color: '#adbac7' }
                            }
                        },
                        scales: {
                            y: {
                                type: 'linear',
                                display: true,
                                position: 'left',
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: '#adbac7' },
                                title: { display: true, text: '직원 수', color: '#2f81f7' }
                            },
                            y1: {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                grid: { drawOnChartArea: false },
                                ticks: { color: '#adbac7' },
                                title: { display: true, text: '임원 수', color: '#bc8cff' }
                            },
                            x: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: '#adbac7' }
                            }
                        }
                    }
                });
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
