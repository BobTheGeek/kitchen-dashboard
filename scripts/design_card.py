"""Print the markup of one Claude Design card. Usage: python3 -I scripts/design_card.py 2a"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "docs" / "design" / "Kitchen Dashboard.dc.html"
html = SRC.read_text()
card = sys.argv[1]
m = re.search(rf'<div class="dv-opt" id="{re.escape(card)}">', html)
if not m:
    sys.exit(f"no card {card}")
end = html.find('<div class="dv-opt"', m.end())
print(re.sub(r"\s+", " ", html[m.start(): end if end > 0 else len(html)]))
