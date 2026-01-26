import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Dashboard HTML Update: Links
dashboard_html_pattern = r'<a href="https://m\.hyundaicard\.com/mp/ev/MPEV0101_01\.hc" target="_blank" class="card-link" data-name="현대카드">'
dashboard_html_replacement = r'<a href="/card-events/hyundai" class="card-link" data-name="현대카드">'
content = re.sub(dashboard_html_pattern, dashboard_html_replacement, content)

dashboard_html_pattern2 = r'<a href="https://www\.lottecard\.co\.kr/app/LPBNNEA_V100\.lc" target="_blank" class="card-link" data-name="롯데카드">'
dashboard_html_replacement2 = r'<a href="/card-events/lotte" class="card-link" data-name="롯데카드">'
content = re.sub(dashboard_html_pattern2, dashboard_html_replacement2, content)

# 2. Dashboard JS Update: fetchAllEvents
# Find [shinhanRes, kbRes, ..., samsungRes] and add hyundaiRes, lotteRes
js_res_pattern = r'\[shinhanRes, kbRes, hanaRes, wooriRes, bcRes, samsungRes\]'
js_res_replacement = r'[shinhanRes, kbRes, hanaRes, wooriRes, bcRes, samsungRes, hyundaiRes, lotteRes]'
content = re.sub(js_res_pattern, js_res_replacement, content)

js_fetch_pattern = r"fetch\('/api/samsung-cards'\)"
js_fetch_replacement = r"fetch('/api/samsung-cards'),\n                        fetch('/api/hyundai-cards'),\n                        fetch('/api/lotte-cards')"
content = re.sub(js_fetch_pattern, js_fetch_replacement, content)

js_data_pattern = r"const samsungData = await samsungRes\.json\(\);"
js_data_replacement = r"const samsungData = await samsungRes.json();\n                    const hyundaiData = await hyundaiRes.json();\n                    const lotteData = await lotteRes.json();"
content = re.sub(js_data_pattern, js_data_replacement, content)

js_norm_pattern = r"const samsung = normalize\(samsungData, \"삼성카드\"\);"
js_norm_replacement = r"const samsung = normalize(samsungData, '삼성카드');\n                    const hyundai = normalize(hyundaiData, '현대카드');\n                    const lotte = normalize(lotteData, '롯데카드');"
content = re.sub(js_norm_pattern, js_norm_replacement, content)

js_all_pattern = r"allEvents = \[\.\.\.shinhan, \.\.\.kb, \.\.\.hana, \.\.\.woori, \.\.\.bc, \.\.\.samsung\];"
js_all_replacement = r"allEvents = [...shinhan, ...kb, ...hana, ...woori, ...bc, ...samsung, ...hyundai, ...lotte];"
content = re.sub(js_all_pattern, js_all_replacement, content)

# 3. Add Internal Routes for Hyundai and Lotte
# I'll create a generic template function and then define the routes

template_js = """
        <script>
            let allEvents = [];

            async function updateData() {
                const path = window.location.pathname.split("/").pop();
                try {
                    await fetch(`/api/${path}/update`, {method:"POST"});
                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");
                } catch(e) {}
            }

            async function fetchEvents() {
                try {
                    const response = await fetch('/api/API_PATH');
                    const json = await response.json();
                    if(json.last_updated) document.getElementById('lastUpdated').innerText = `Update: ${json.last_updated.substring(5,16)}`;
                    allEvents = Array.isArray(json) ? json : (json.data || []);
                    renderEvents(allEvents);
                } catch (error) {
                    document.getElementById('eventList').innerHTML = '<div class="loading">정보를 불러오지 못했습니다.</div>';
                }
            }

            function parseQuery(q) {
                const terms = {and:[], or:[]};
                const re = /"([^"]+)"/g;
                let m, left=q;
                while((m=re.exec(q))!==null){ terms.and.push(m[1]); left=left.replace(m[0],''); }
                const split = left.trim().split(/\s+/).filter(x=>x);
                if(split.length>0) terms.or = split;
                return terms;
            }
            function match(ev, terms) {
                const txt = ((ev.eventName||"")+" "+(ev.category||"")).toLowerCase();
                for(const t of terms.and) if(!txt.includes(t)) return false;
                if(terms.or && terms.or.length > 0) {
                    let hit = false;
                    for(const t of terms.or) if(txt.includes(t)) { hit=true; break; }
                    if(!hit) return false;
                }
                return true;
            }
            function filterEvents() {
                const search = document.getElementById('searchInput').value.toLowerCase();
                const terms = parseQuery(search);
                const filtered = allEvents.filter(ev => match(ev, terms));
                renderEvents(filtered);
            }

            function renderEvents(events) {
                const list = document.getElementById('eventList');
                const stats = document.getElementById('stats');
                stats.innerText = `총 ${events.length}개의 이벤트`;
                if (events.length === 0) {
                    list.innerHTML = '<div class="loading">이벤트가 없습니다.</div>';
                    return;
                }
                list.innerHTML = events.map(ev => `
                    <a href="${ev.link}" target="_blank" class="event-card" referrerpolicy="no-referrer" rel="noreferrer noopener">
                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy">` : ""}
                        <div class="event-category-row">
                            <span style="background:#f5f5f7;padding:5px 10px;border-radius:8px;font-weight:600;font-size:0.75rem;color:#6e6e73;letter-spacing:-0.01em">${ev.category}</span>
                            <div style="width:10px;height:10px;border-radius:50%;background:${ev.bgColor}"></div>
                        </div>
                        <div class="event-title">${ev.eventName}</div>
                        <div class="event-date">${ev.period}</div>
                    </a>
                `).join('');
            }
            fetchEvents();
        </script>
"""

# Common CSS/HTML parts
common_head = """
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>COMPANY_NAME 이벤트 검색</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #F5F5F7;
                --accent-color: #1d1d1f !important;
                --text-secondary: #6e6e73;
                --blue-color: #0071e3;
                --border-color: rgba(0,0,0,0.1);
            }
            body { background-color: var(--bg-color); color: var(--accent-color); font-family: 'Inter', sans-serif; padding-bottom: 50px; }
            .nav-header { position: sticky; top: 0; background: rgba(245, 245, 247, 0.8); backdrop-filter: blur(20px); z-index: 100; padding: 1rem; border-bottom: 1px solid var(--border-color); }
            .nav-content { max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
            .back-btn { text-decoration: none; color: var(--blue-color); font-weight: 500; }
            .main-content { max-width: 1400px; margin: 2rem auto; padding: 0 1.5rem; }
            h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin-bottom: 1.5rem; }
            .search-section { display: flex; gap: 1rem; margin-bottom: 2rem; }
            .search-input { flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color); box-shadow: 0 2px 4px rgba(0,0,0,0.02); outline: none; transition: all 0.2s; font-size: 0.95rem; }
            .search-input:focus { border-color: var(--blue-color); box-shadow: 0 0 0 4px rgba(0,113,227,0.1); }
            .event-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1.25rem; margin-top: 1rem; }
            .event-card { background: white; border-radius: 18px; padding: 1.5rem; display: flex; flex-direction: column; justify-content: space-between; border: 1px solid rgba(0,0,0,0.08); text-decoration: none; color: inherit; transition: all 0.2s ease; height: 100%; min-height: 180px; position: relative; box-sizing: border-box; }
            .event-card:hover { transform: translateY(-4px); box-shadow: 0 8px 20px rgba(0,0,0,0.06); border-color: rgba(0,0,0,0.12); }
            .event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }
            .event-category-row { width: 100%; display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
            .event-title { font-size: 1.05rem; font-weight: 700; color: #1d1d1f !important; margin-bottom: 1rem; line-height: 1.45; letter-spacing: -0.01em; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; word-break: keep-all; flex: 1; }
            .event-date { font-size: 0.8rem; color: #86868b; letter-spacing: -0.01em; margin-top: auto; }
            .loading { text-align: center; padding: 4rem; color: var(--text-secondary); font-size: 0.95rem; grid-column: 1 / -1; }
            .stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.8rem; text-align: right; }
        </style>
    </head>
"""

common_body = """
    <body>
        <div class="nav-header">
            <div class="nav-content">
                <a href="/card-events" class="back-btn">← 카드사 목록</a>
                <div style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
                    COMPANY_NAME 이벤트
                    <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; display:flex;">🔄</button>
                </div>
                <div id="lastUpdated" style="font-size: 0.8rem; color: var(--text-secondary); min-width: 80px; text-align: right;"></div>
            </div>
        </div>
        <div class="main-content">
            <h1>이벤트 전체 검색</h1>
            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="관심 있는 이벤트를 검색해보세요..." onkeyup="filterEvents()">
            </div>
            <div id="stats" class="stats"></div>
            <div id="eventList" class="event-list">
                <div class="loading">이벤트를 불러오는 중입니다...</div>
            </div>
        </div>
"""

def generate_route(company_name, api_path):
    head = common_head.replace("COMPANY_NAME", company_name)
    body = common_body.replace("COMPANY_NAME", company_name)
    script = template_js.replace("API_PATH", api_path)
    return f"""
@app.get("/card-events/{api_path.split('-')[0]}", response_class=HTMLResponse)
def {api_path.replace('-', '_')}_page():
    html_content = \"\"\"
    <!DOCTYPE html>
    <html lang="ko">
    {head}
    {body}
    {script}
    </body>
    </html>
    \"\"\"
    return HTMLResponse(content=html_content)
"""

hyundai_route = generate_route("현대카드", "hyundai-cards")
lotte_route = generate_route("롯데카드", "lotte-cards")

# Append these routes before the end of the file
# Or before common routes like /health or similar
# I'll just append them at the end of the file before the scheduler part or similar
if lotte_route not in content:
    content += "\n" + hyundai_route + "\n" + lotte_route

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated Dashboard and added internal routes for Hyundai and Lotte.")
