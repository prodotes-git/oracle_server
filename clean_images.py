import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove all existing image tags in a specific pattern to start fresh
content = re.sub(r'\$\{ev\.image \? `<img src="\$\{ev\.image\}" class="event-image" loading="lazy" onerror="this\.style\.display=.none.">` : ..\}', '', content)
content = re.sub(r'\$\{ev\.image \? `<img src="\$\{ev\.image\}" class="event-image" loading="lazy" onerror="this\.style\.display=\\x27none\\x27">` : \\x27\\x27\}', '', content)

# 2. Add back the clean image tag exactly once
render_pattern = r'(<a href="\$\{ev\.link\}"[^>]*>)'
render_replacement = r'\1\n                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy">` : ""}'
content = re.sub(render_pattern, render_replacement, content)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Cleaned up images in main.py")
