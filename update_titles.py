import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix titles to be more descriptive and less confusing
# Just use simple replacements without complex regex for now
replacements = [
    ("<h1>이벤트 전체 검색</h1>", "<h1>신한카드 이벤트 검색</h1>"), # Shinhan
    ("<h1>이벤트 전체 검색</h1>", "<h1>KB국민카드 이벤트 검색</h1>"), # KB
    ("<h1>이벤트 전체 검색</h1>", "<h1>하나카드 이벤트 검색</h1>"), # Hana
    ("<h1>이벤트 전체 검색</h1>", "<h1>우리카드 이벤트 검색</h1>"), # Woori
    ("<h1>이벤트 전체 검색</h1>", "<h1>BC카드 이벤트 검색</h1>"),   # BC
    ("<h1>이벤트 전체 검색</h1>", "<h1>삼성카드 이벤트 검색</h1>"), # Samsung
    ("<h1>이벤트 전체 검색</h1>", "<h1>현대카드 이벤트 검색</h1>"), # Hyundai
    ("<h1>이벤트 전체 검색</h1>", "<h1>롯데카드 이벤트 검색</h1>"), # Lotte
]

for old, new in replacements:
    content = content.replace(old, new, 1)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated page titles for better clarity.")
