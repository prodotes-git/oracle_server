import re

with open("main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

def find_func_end(lines, start_idx):
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("@app.") or lines[i].startswith("async def ") or lines[i].startswith("def "):
            return i
    return len(lines)

# Map endpoints to their cache keys and file paths
updates = {
    "@app.get(\"/api/shinhan-cards\")": ("SHINHAN_CACHE_KEY", "shinhan_data.json"),
    "@app.get(\"/api/kb-cards\")": ("KB_CACHE_KEY", "kb_data.json"),
    "@app.get(\"/api/hana-cards\")": ("HANA_CACHE_KEY", "hana_data.json"),
    "@app.get(\"/api/woori-cards\")": ("WOORI_CACHE_KEY", "woori_data.json"),
    "@app.get(\"/api/bc-cards\")": ("BC_CACHE_KEY", "bc_data.json"),
    "@app.get(\"/api/samsung-cards\")": ("SAMSUNG_CACHE_KEY", "samsung_data.json"),
}

new_lines = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    match_found = False
    for signature, (key, file) in updates.items():
        if signature in line:
            # Add the header and the new clean body
            new_lines.append(lines[i]) # @app.get...
            new_lines.append(lines[i+1]) # async def ... (assuming next line)
            new_lines.append(f"    return get_cached_data({key}, '{file}')\n\n")
            # Skip the old body
            i = find_func_end(lines, i + 1)
            match_found = True
            break
    
    if not match_found:
        new_lines.append(lines[i])
        i += 1

with open("main.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("Refactored all API endpoints to use get_cached_data for clean de-duplication.")
