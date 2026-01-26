import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add updateData function to all pages (if missing)
# Pages: shinobi, kb, hana, woori, bc, samsung
companies = ['kb', 'hana', 'woori', 'bc', 'samsung', 'shinhan']

for comp in companies:
    func_name = f"updateData_{comp}" # Unique name to avoid confusion in my search
    if f"function updateData" not in content: # This is too generic
        pass

# Actually, I'll just look for fetchEvents and prepend updateData
update_func_template = """
            async function updateData() {
                try {
                    await fetch('/api/COMP_ID/update', {method:'POST'});
                    alert('데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.');
                } catch(e) {}
            }
"""

for comp in companies:
    # Find the block for each card company
    # I'll look for fetch('/api/COMP-cards')
    api_call = f"fetch('/api/{comp}-cards')"
    if api_call in content:
        # Check if updateData is already in this script block
        # I'll just insert it before fetchEvents
        pattern = r'(async function fetchEvents\(\))'
        # We need to make sure we are in the right company's script block
        # This is getting complex. I'll just do it manually for the header.
        pass

# 2. Add Refresh button to the header
# Target: <div style="font-weight: 600;">COMPANY NAME 이벤트</div>
header_pattern = r'(<div style="font-weight: 600;">)([^<]+ 이벤트)(</div>)'
header_replacement = r'\1 \2 <button onclick="updateData()" style="background:none; border:none; cursor:pointer; font-size:1.1rem; padding:0; margin-left:8px;">🔄</button>\3'
content = re.sub(header_pattern, header_replacement, content)

# 3. Ensure updateData function exists in all pages
# I'll just add it to the start of EVERY <script> tag that has fetchEvents
script_pattern = r'(<script>\s+let allEvents = \[\];)'
script_replacement = r'\1\n\n            async function updateData() {\n                const path = window.location.pathname.split("/").pop();\n                try {\n                    await fetch(`/api/${path}/update`, {method:"POST"});\n                    alert("데이터 갱신을 시작했습니다. 10초 후 새로고침 해주세요.");\n                } catch(e) {}\n            }'
content = re.sub(script_pattern, script_replacement, content)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Added refresh buttons globally")
