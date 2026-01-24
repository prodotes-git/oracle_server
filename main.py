from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import os
import redis

app = FastAPI()

# Redis 연결 설정
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        visits = r.incr("counter")
    except Exception:
        visits = "---"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Oracle Server | Premium Experience</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-color: #000000;
                --card-bg: rgba(255, 255, 255, 0.05);
                --accent-color: #ffffff;
                --text-secondary: #86868b;
                --glass-border: rgba(255, 255, 255, 0.1);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                -webkit-font-smoothing: antialiased;
            }}
            
            body {{
                background-color: var(--bg-color);
                color: white;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                overflow: hidden;
                background: radial-gradient(circle at center, #1a1a1a 0%, #000000 100%);
            }}

            .container {{
                padding: 2rem;
                width: 100%;
                max-width: 500px;
                text-align: center;
                animation: fadeIn 1.2s ease-out;
            }}

            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}

            .glass-card {{
                background: var(--card-bg);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border);
                border-radius: 32px;
                padding: 3rem 2rem;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            }}

            h1 {{
                font-family: 'Outfit', sans-serif;
                font-size: 2.5rem;
                font-weight: 600;
                letter-spacing: -0.02em;
                margin-bottom: 0.5rem;
                background: linear-gradient(180deg, #FFFFFF 0%, #A1A1A1 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}

            .status-badge {{
                display: inline-block;
                padding: 0.5rem 1rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 100px;
                font-size: 0.75rem;
                color: var(--text-secondary);
                margin-bottom: 2rem;
                text-transform: uppercase;
                letter-spacing: 0.1em;
            }}

            .visits-label {{
                font-size: 0.9rem;
                color: var(--text-secondary);
                margin-top: 2rem;
                font-weight: 300;
            }}

            .visits-count {{
                font-family: 'Outfit', sans-serif;
                font-size: 3.5rem;
                font-weight: 600;
                margin-top: 0.5rem;
                color: var(--accent-color);
            }}

            .footer-text {{
                position: fixed;
                bottom: 2rem;
                font-size: 0.8rem;
                color: var(--text-secondary);
                letter-spacing: 0.05em;
            }}

            .dot {{
                display: inline-block;
                width: 8px;
                height: 8px;
                background-color: #30d158;
                border-radius: 50%;
                margin-right: 8px;
                box-shadow: 0 0 10px #30d158;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="glass-card">
                <div class="status-badge">
                    <span class="dot"></span> Oracle Cloud Project
                </div>
                <h1>System Active</h1>
                <p style="color: var(--text-secondary); font-weight: 300;">Experience the power of Minimalism</p>
                
                <div class="visits-label">Total Interactions</div>
                <div class="visits-count">{visits}</div>
            </div>
        </div>
        <div class="footer-text">DESIGNED BY ANTIGRAVITY</div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/health")
def health_check():
    return {"status": "ok"}
