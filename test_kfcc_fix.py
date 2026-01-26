import asyncio
import json
import os
import sys
from kfcc_crawler import run_crawler

async def test_crawler():
    # Only crawl Seoul to verify fix
    import kfcc_crawler
    kfcc_crawler.ALL_REGIONS = [
        ["서울", "강남구", "마포구"]
    ]
    data = await run_crawler()
    print(f"Collected {len(data)} records.")
    if data:
        print(f"First record: {data[0]}")
        with open("kfcc_data_test.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

asyncio.run(test_crawler())
