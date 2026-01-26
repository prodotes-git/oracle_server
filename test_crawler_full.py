import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.getcwd())

async def test_crawler():
    try:
        from kfcc_crawler import run_crawler
        print("Starting crawler test...")
        data = await run_crawler()
        print(f"Crawler finished. Collected {len(data)} records.")
        if data:
            print(f"First record: {data[0]}")
            # Check if rates are populated
            if data[0].get('rates'):
                print(f"Rates for first bank: {data[0]['rates']}")
        return data
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(test_crawler())
    if result:
        print(f"\n✅ Success! Total banks: {len(result)}")
    else:
        print("\n❌ Failed!")
