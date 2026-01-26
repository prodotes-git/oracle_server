import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove the misplaced helper function and fix the headers dict
helper_code = """
def get_cached_data(cache_key, file_path):
    try:
        if r:
            cached = r.get(cache_key)
            if cached: return json.loads(cached)
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            unique_data = []
            seen = set()
            for item in data:
                name = item.get('eventName')
                if name and name not in seen:
                    seen.add(name)
                    unique_data.append(item)
            mtime = os.path.getmtime(file_path)
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            res = {'last_updated': last_updated, 'data': unique_data}
            if r: r.setex(cache_key, CACHE_EXPIRE, json.dumps(res))
            return res
    except Exception: pass
    return {'last_updated': None, 'data': []}
"""

# Find and remove the misplaced one
content = content.replace(helper_code, "")

# Ensure headers dict is intact (remove the gap I introduced)
content = content.replace('"Referer": f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc",\n\n\n\n', '"Referer": f"{base_url}/mob/MOBFM501N/MOBFM501R31.shc",\n')

# 2. Add the helper at the top level
content = content.replace("CACHE_EXPIRE = 3600  # 1시간 동안 캐시 유지", "CACHE_EXPIRE = 3600  # 1시간 동안 캐시 유지\n" + helper_code)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed misplaced get_cached_data")
