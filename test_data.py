import json
import os

KB_CACHE_KEY = "kb_card_events_cache_v1"
SAMSUNG_CACHE_KEY = "samsung_card_events_cache_v1"

def test_kb():
    file_path = 'kb_data.json'
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"KB file exists, items: {len(data)}")
        if len(data) > 0:
            print(f"First item: {data[0]}")
    else:
        print("KB file does not exist")

def test_samsung():
    file_path = 'samsung_data.json'
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Samsung file exists, items: {len(data)}")
    else:
        print("Samsung file does not exist")

test_kb()
test_samsung()
