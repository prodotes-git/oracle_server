import asyncio
import sys
import os
import json
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.getcwd())

import card_events
from shared import seoul_tz

async def test_all_card_crawlers():
    crawlers = [
        ("Shinhan", card_events.crawl_shinhan_bg),
        ("KB", card_events.crawl_kb_bg),
        ("Hana", card_events.crawl_hana_bg),
        ("Woori", card_events.crawl_woori_bg),
        ("BC", card_events.crawl_bc_bg),
        ("Samsung", card_events.crawl_samsung_bg),
        ("Hyundai", card_events.crawl_hyundai_bg),
        ("Lotte", card_events.crawl_lotte_bg)
    ]
    
    results = {}
    
    for name, crawler_func in crawlers:
        print(f"\n--- Testing {name} Crawler ---")
        try:
            # Note: these functions write to files and redis
            await crawler_func()
            
            # Check the resulting file
            file_name = f"{name.lower()}_data.json"
            if os.path.exists(file_name):
                with open(file_name, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    if isinstance(data, dict) and "data" in data:
                        raw_list = data["data"]
                        last_updated = data.get("last_updated", "N/A")
                    else:
                        raw_list = data
                        last_updated = "N/A (Legacy Format)"
                        
                    count = len(raw_list)
                    print(f"✅ {name} Success: {count} events found. Last updated: {last_updated}")
                    results[name] = {"count": count, "status": "Success"}
            else:
                print(f"❌ {name} Failed: Data file not found.")
                results[name] = {"count": 0, "status": "File Not Found"}
                
        except Exception as e:
            print(f"❌ {name} Error: {e}")
            import traceback
            traceback.print_exc()
            results[name] = {"count": 0, "status": f"Error: {str(e)}"}
            
    print("\n" + "="*40)
    print("FINAL CRAWLER TEST RESULTS")
    print("="*40)
    for name, res in results.items():
        print(f"{name:10}: {res['status']} ({res['count']} events)")
    print("="*40)

if __name__ == "__main__":
    asyncio.run(test_all_card_crawlers())
