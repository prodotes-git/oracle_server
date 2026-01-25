# 우리카드 크롤러 (추가)
async def crawl_woori_bg():
    try:
        print(f"[{datetime.now()}] Starting Woori background crawl...")
        all_events = []
        base_url = "https://m.wooricard.com"
        api_url = f"{base_url}/dcmw/yh1/bnf/bnf02/prgevnt/getPrgEvntList.pwkjson"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                "Content-Type": "application/json"
            }
            
            # 페이지별로 데이터 수집
            for page_idx in range(1, 20):  # 최대 20페이지
                payload = {
                    "bnf02PrgEvntVo": {
                        "evntCtgrNo": "",
                        "searchKwrd": "",
                        "sortOrd": "orderNew",
                        "pageIndex": str(page_idx),
                        "pageSize": "20",
                        "evntItgCfcd": ""
                    }
                }
                
                try:
                    response = await client.post(api_url, json=payload, headers=headers)
                    if response.status_code != 200:
                        break
                        
                    res_json = response.json()
                    event_list = res_json.get("prgEvntList", [])
                    
                    if not event_list:
                        break
                        
                    for ev in event_list:
                        title = ev.get("cardEvntNm", "") or ev.get("mblDocTitlTxt", "")
                        start_date = ev.get("evntSdt", "")
                        end_date = ev.get("evntEdt", "")
                        
                        # 날짜 포맷팅 (YYYYMMDD -> YYYY.MM.DD)
                        if len(start_date) == 8:
                            start_date = f"{start_date[:4]}.{start_date[4:6]}.{start_date[6:]}"
                        if len(end_date) == 8:
                            end_date = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:]}"
                        
                        img_path = ev.get("fileCoursWeb", "")
                        if img_path and not img_path.startswith("http"):
                            img_path = f"{base_url}{img_path}"
                            
                        # 우리카드는 sessionStorage 사용으로 직접 링크 어려움
                        # 목록 페이지로 링크
                        link = f"{base_url}/dcmw/yh1/bnf/bnf02/prgevnt/M1BNF202S00.do"
                        
                        all_events.append({
                            "category": "우리카드",
                            "eventName": title,
                            "period": f"{start_date} ~ {end_date}",
                            "link": link,
                            "image": img_path,
                            "bgColor": "#ffffff"
                        })
                        
                except Exception as e:
                    print(f"Error parsing Woori page {page_idx}: {e}")
                    break

        if all_events:
            try:
                with open("woori_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"Woori file save failed: {fe}")

            if r:
                try:
                    r.setex(WOORI_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                     print(f"Woori Redis save failed: {re}")
            
            print(f"[{datetime.now()}] Woori crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] Woori crawl failed: {e}")


# BC카드 크롤러 (추가)
async def crawl_bc_bg():
    try:
        print(f"[{datetime.now()}] Starting BC background crawl...")
        all_events = []
        base_url = "https://web.paybooc.co.kr"
        target_url = f"{base_url}/web/evnt/main"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = await client.get(target_url, headers=headers)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "lxml")
                
                # BC카드 이벤트 아이템 선택자 (실제 페이지 구조에 맞게 조정 필요)
                items = soup.select(".event-list .event-item, .evnt-list .item, article.event")
                
                for item in items:
                    try:
                        # 제목
                        title_elem = item.select_one(".title, .event-title, h3, h4")
                        title = title_elem.text.strip() if title_elem else ""
                        
                        # 이미지
                        img_elem = item.select_one("img")
                        img_src = img_elem.get("src", "") if img_elem else ""
                        if img_src and not img_src.startswith("http"):
                            img_src = f"{base_url}{img_src}"
                        
                        # 링크
                        link_elem = item.select_one("a")
                        link = link_elem.get("href", "") if link_elem else ""
                        if link and not link.startswith("http"):
                            link = f"{base_url}{link}"
                        
                        # 기간
                        period_elem = item.select_one(".period, .date, .event-period")
                        period = period_elem.text.strip() if period_elem else ""
                        
                        if title:  # 제목이 있는 경우만 추가
                            all_events.append({
                                "category": "BC카드",
                                "eventName": title,
                                "period": period,
                                "link": link or target_url,
                                "image": img_src,
                                "bgColor": "#ffffff"
                            })
                    except Exception:
                        continue

        if all_events:
            try:
                with open("bc_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"BC file save failed: {fe}")

            if r:
                try:
                    r.setex(BC_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                     print(f"BC Redis save failed: {re}")
            
            print(f"[{datetime.now()}] BC crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] BC crawl failed: {e}")


# 삼성카드 크롤러 (추가)
async def crawl_samsung_bg():
    try:
        print(f"[{datetime.now()}] Starting Samsung background crawl...")
        all_events = []
        base_url = "https://www.samsungcard.com"
        target_url = f"{base_url}/personal/event/ing/UHPPBE1401M0.jsp"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = await client.get(target_url, headers=headers)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "lxml")
                
                # 삼성카드 이벤트 아이템 선택자 (실제 페이지 구조에 맞게 조정 필요)
                items = soup.select(".event-list li, .list-event .item, .evt-list .evt-item")
                
                for item in items:
                    try:
                        # 제목
                        title_elem = item.select_one(".title, .evt-title, strong, .tit")
                        title = title_elem.text.strip() if title_elem else ""
                        
                        # 이미지
                        img_elem = item.select_one("img")
                        img_src = img_elem.get("src", "") if img_elem else ""
                        if img_src and not img_src.startswith("http"):
                            if img_src.startswith("//"):
                                img_src = f"https:{img_src}"
                            else:
                                img_src = f"{base_url}{img_src}"
                        
                        # 링크
                        link_elem = item.select_one("a")
                        link = link_elem.get("href", "") if link_elem else ""
                        if link and not link.startswith("http"):
                            link = f"{base_url}{link}"
                        
                        # 기간
                        period_elem = item.select_one(".period, .date, .evt-period")
                        period = period_elem.text.strip() if period_elem else ""
                        
                        if title:  # 제목이 있는 경우만 추가
                            all_events.append({
                                "category": "삼성카드",
                                "eventName": title,
                                "period": period,
                                "link": link or target_url,
                                "image": img_src,
                                "bgColor": "#ffffff"
                            })
                    except Exception:
                        continue

        if all_events:
            try:
                with open("samsung_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False)
            except Exception as fe:
                print(f"Samsung file save failed: {fe}")

            if r:
                try:
                    r.setex(SAMSUNG_CACHE_KEY, CACHE_EXPIRE, json.dumps({"last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "data": all_events}))
                except Exception as re:
                     print(f"Samsung Redis save failed: {re}")
            
            print(f"[{datetime.now()}] Samsung crawl finished. {len(all_events)} events.")
            
    except Exception as e:
        print(f"[{datetime.now()}] Samsung crawl failed: {e}")
