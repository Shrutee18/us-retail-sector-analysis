import json
from pathlib import Path

CHECKS = {
    "KR": ["cost", "inventor", "merchandise", "sellinggeneral", "operatingexpense"],
    "TGT": ["netincome", "profitloss"],
}
for t, words in CHECKS.items():
    facts = json.loads(Path(f"data/raw/companyfacts_{t}.json").read_text())
    print(f"\n=== {t} ===")
    for taxo, tags in facts["facts"].items():
        for tag, d in sorted(tags.items()):
            if not any(w in tag.lower() for w in words):
                continue
            items = d.get("units", {}).get("USD", [])
            annual = [i for i in items if i.get("form") in ("10-K", "10-K/A") and i.get("fp") == "FY"]
            ends = sorted({i["end"] for i in annual if i["end"] >= "2019-01-01"})
            if ends:
                print(f"{taxo}:{tag}  ({len(ends)} period ends)  {ends if t == 'TGT' else ends[-1]}")
