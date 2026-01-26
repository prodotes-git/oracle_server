import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add event-image CSS to all card pages (if missing)
# Target: style block with .event-category-row
css_pattern = r'(\.event-category-row\s*\{[^}]+\})'
css_replacement = r'.event-image { width: 100%; height: 120px; object-fit: cover; border-radius: 12px; margin-bottom: 1rem; background: #f5f5f7; }\n            \1'
# But only if .event-image is not already there
if ".event-image" not in content:
    content = re.sub(css_pattern, css_replacement, content)

# 2. Add image to renderEvents templates
render_pattern = r'(list\.innerHTML = events\.map\(ev => `\s*<a href="\$\{ev\.link\}"[^>]*>)'
render_replacement = r'\1\n                        ${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display=\'none\'">` : \'\'}'
content = re.sub(render_pattern, render_replacement, content)

# 3. Add Refresh button and updateData function logic
# This part is harder with regex because of variety.
# I'll just focus on Shinhan specifically since it's the priority.

# Fix Shinhan Title logic to be cleaner
content = content.replace(
    "title = f\"{sub_title} {title}\"",
    "title = f\"{title} ({sub_title})\" if sub_title else title"
)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Applied fixes to main.py")
