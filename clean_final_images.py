import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Specifically target the escaped sequence that remains
pattern_to_remove = r"\$\{ev\.image \? `<img src=\"\$\{ev\.image\}\" class=\"event-image\" loading=\"lazy\" onerror=\"this\.style\.display=\\x27none\\x27\">` : \\x27\\x27\}"
content = re.sub(pattern_to_remove, "", content)

# Also clear the one with backslashes
pattern_to_remove2 = r"\$\{ev\.image \? `<img src=\"\$\{ev\.image\}\" class=\"event-image\" loading=\"lazy\" onerror=\"this\.style\.display=\\\'none\\\'\">` : \\\'\\\'\}"
content = re.sub(pattern_to_remove2, "", content)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Aggressively cleaned up redundant image tags.")
