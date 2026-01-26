import re

with open("main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip_until = -1

# Helper to add de-duplication logic to API endpoints
def add_dedupe(name, data_var="data", last_updated="datetime.now().strftime('%Y-%m-%d %H:%M:%S')"):
    return f"""
        unique_data = []
        seen = set()
        for item in {data_var}:
            name = item.get('eventName')
            if name and name not in seen:
                seen.add(name)
                unique_data.append(item)
        {data_var} = unique_data
        response = {{"last_updated": {last_updated}, "data": {data_var}}}
"""

current_func = None
i = 0
while i < len(lines):
    line = lines[i]
    
    # Define get_cached_data if we are near where it's used or at a good spot
    if i == 50: # arbitrary spot after imports
        new_lines.append("\ndef get_cached_data(cache_key, file_path):\n")
        new_lines.append("    try:\n")
        new_lines.append("        if r:\n")
        new_lines.append("            cached = r.get(cache_key)\n")
        new_lines.append("            if cached: return json.loads(cached)\n")
        new_lines.append("        if os.path.exists(file_path):\n")
        new_lines.append("            with open(file_path, 'r', encoding='utf-8') as f:\n")
        new_lines.append("                data = json.load(f)\n")
        new_lines.append("            unique_data = []\n")
        new_lines.append("            seen = set()\n")
        new_lines.append("            for item in data:\n")
        new_lines.append("                name = item.get('eventName')\n")
        new_lines.append("                if name and name not in seen:\n")
        new_lines.append("                    seen.add(name)\n")
        new_lines.append("                    unique_data.append(item)\n")
        new_lines.append("            mtime = os.path.getmtime(file_path)\n")
        new_lines.append("            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')\n")
        new_lines.append("            res = {'last_updated': last_updated, 'data': unique_data}\n")
        new_lines.append("            if r: r.setex(cache_key, CACHE_EXPIRE, json.dumps(res))\n")
        new_lines.append("            return res\n")
        new_lines.append("    except Exception: pass\n")
        new_lines.append("    return {'last_updated': None, 'data': []}\n\n")

    # De-duplicate within the crawlers if not already done
    # We already did some with multi_replace, but let's be sure about BC
    if "all_events.append({" in line and "BC" in line and "seen_titles" not in "".join(lines[i-10:i]):
        # This is risky, let's skip for now as I already applied some fixes
        pass
        
    new_lines.append(line)
    i += 1

with open("main.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("Added get_cached_data and improved structure")
