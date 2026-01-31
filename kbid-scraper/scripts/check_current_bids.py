import csv
import re
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[1] / 'results' / 'test_kbid_auction_1.csv'

if not CSV_PATH.exists():
    print(f"CSV not found: {CSV_PATH}")
    raise SystemExit(1)

bad = []

with CSV_PATH.open(newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        cb = (row.get('current_bid') or '').strip()
        # Acceptable form: digits + dot + two decimals (e.g., 9.00)
        if not re.match(r'^\d+\.\d{2}$', cb):
            bad.append((i, row.get('lot_number'), cb, row.get('item_url')))

print(f"Total rows scanned: {i}")
print(f"Suspicious current_bid rows: {len(bad)}\n")
if bad:
    print("First 30 suspicious rows (line, lot_number, current_bid, item_url):")
    for b in bad[:30]:
        print(b)
