import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to find the specialized image tag with onerror or just simple one
# and replace it with a single, clean image tag including onerror for robustness.
# We want to catch cases where there are multiple tags in a row.

# This regex finds any sequence of image interpolation tags and replaces it with one.
# It handles both \x27 (apostrophe) and simple '
# It handles various quote types (double, single, backtick) used inside.

clean_img_tag = '${ev.image ? `<img src="${ev.image}" class="event-image" loading="lazy" onerror="this.style.display=\'none\'">` : ""}'

# Use a multi-pass approach to clear duplicates
# First, remove the redundant ones
content = re.sub(r'\$\{ev\.image \? `<img src="\$\{ev\.image\}" class="event-image" loading="lazy" onerror="this\.style\.display=.none.">` : ..\}', '', content)
content = re.sub(r'\$\{ev\.image \? `<img src="\$\{ev\.image\}" class="event-image" loading="lazy">` : ..\}', '', content)

# Now, ensure there's exactly one clean tag after <a href="...">
# This regex looks for the <a> tag and puts the clean image tag right after it.
# We use a non-greedy approach for the <a> tag.
content = re.sub(r'(<a href="\$\{ev\.link\}"[^>]*>)\s*', r'\1\n                        ' + clean_img_tag + r'\n                        ', content)

# Final cleanup: sometimes multiple replacements happen if there were already newlines.
# I'll do a simple string replacement for any accidental triple-images if the regex fails.
# But the regex above should be fairly solid as it replaces the whole block after the <a> tag.

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Cleaned up all duplicate image tags.")
