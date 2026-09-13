#!/usr/bin/env python3
import os
import re
import sys
import tempfile
from datetime import datetime

if len(sys.argv) < 2:
    sys.stderr.write("usage: path.py <tmpdir> [topic]\n")
    sys.exit(1)
tmpdir = sys.argv[1] or tempfile.gettempdir()
topic = sys.argv[2] if len(sys.argv) > 2 else "task"
topic = re.sub(r"[^\w-]+", "-", topic, flags=re.UNICODE).strip("-")[:40] or "task"
date = datetime.now().strftime("%Y%m%d")
base = os.path.join(tmpdir, "handoff")
os.makedirs(base, exist_ok=True)
path = os.path.join(base, f"{date}-{topic}.md")
if os.path.exists(path):
    path = os.path.join(base, f"{date}-{topic}-{datetime.now().strftime('%H%M%S')}.md")
print(path)
