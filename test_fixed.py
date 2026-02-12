import asyncio
import sys
import os
import json
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.getcwd())

import card_events
from shared import seoul_tz

async def test_fixed_crawlers():
    crawlers = [
        ("Hana", card_events.crawl_hana_bg),
        ("Woori", card_events.crawl_woori_bg),
    ]
    
    for name, crawler_func in crawlers:
        print(f"\n--- Testing {name} Crawler ---")
        try:
            await crawler_func()
            file_name = f"{name.lower()}_data.json"
            if os.path.exists(file_name):
                with open(file_name, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    count = len(data.get("data", []))
                    last_updated = data.get("last_updated", "N/A")
                    print(f"✅ {name} Success: {count} events found. Last updated: {last_updated}")
            else:
                print(f"❌ {name} Failed: Data file not found.")
        except Exception as e:
            print(f"❌ {name} Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_fixed_crawlers())
