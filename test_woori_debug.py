import asyncio
from playwright.async_api import async_playwright

async def test_woori():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent="Mozilla/5.0")
        page = await ctx.new_page()
        print(f"Page object: {page}")
        print(f"dir(page): {dir(page)}")
        try:
            print("Navigating...")
            await page.goto("https://m.wooricard.com/dcmw/yh1/bnf/bnf02/prgevnt/M1BNF202S00.do", timeout=30000)
            print("Waiting for response...")
            # Using wait_for_event for debugging if wait_for_response fails
            res = await page.wait_for_response(lambda r: "getPrgEvntList.pwkjson" in r.url, timeout=30000)
            print(f"Response status: {res.status}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_woori())
