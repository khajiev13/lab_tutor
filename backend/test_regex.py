"""Quick test for the updated _SECTION_HEADING_RE."""

import re

_SECTION_HEADING_RE = re.compile(
    r"^(?:#{1,4}\s+)?(?:\*\*)?(\d{1,2}\.\d{1,2})\.?\s+"
    r"([A-Z][\w\s,'\-:;&/()?.\"]{2,80}?)"
    r"(?:\*\*)?\s*$",
    re.MULTILINE,
)

tests = [
    ("1.1 What is Data Mining?", True),
    ("## 1.1 What is Data Mining?", True),
    ("### 1.1 What is Data Mining?", True),
    ("**1.1 What is Data Mining?**", True),
    ("## **1.1 What is Data Mining?**", True),
    ("10.2 Title With Commas, Hyphens - and Colons: Yes", True),
    ("1.2 Statistical Limits on Data Mining", True),
    ("3.1.3 Collaborative Filtering", False),  # X.Y.Z — too deep
    ("1.1 lowercase title", False),  # starts lowercase
    ("## 2.3 Query Processing", True),
    ("#### 5.1.2 Definition of PageRank", False),  # X.Y.Z — too deep
    ("3.10 Summary of Chapter 3", True),
    ("## 3.9 Methods for High Degrees of Similarity", True),
]

for text, should_match in tests:
    m = _SECTION_HEADING_RE.search(text)
    matched = m is not None
    ok = "OK" if matched == should_match else "FAIL"
    detail = ""
    if m:
        detail = f" -> num={m.group(1)!r}, title={m.group(2)!r}"
    print(f"  [{ok}] {'MATCH' if matched else 'MISS ':5s} {text!r}{detail}")
