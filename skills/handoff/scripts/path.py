#!/usr/bin/env python3
import os
import re
import sys
from datetime import datetime

topic = sys.argv[1] if len(sys.argv) > 1 else "task"
topic = re.sub(r"[^\w-]+", "-", topic, flags=re.UNICODE).strip("-")[:40] or "task"
date = datetime.now().strftime("%Y%m%d")
base = os.path.join(
    os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp",
    "opencode",
    "handoff",
)
os.makedirs(base, exist_ok=True)
path = os.path.join(base, f"{date}-{topic}.md")
if os.path.exists(path):
    path = os.path.join(base, f"{date}-{topic}-{datetime.now().strftime('%H%M%S')}.md")
print(path)
