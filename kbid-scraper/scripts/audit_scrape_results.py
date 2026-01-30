"""
Lightweight audit script for scraped CSV results from kbid_scraper

Usage:
    python audit_scrape_results.py path/to/kbid_auctions_data.csv

What it does:
- Reads CSV output produced by `kbid_scraper.py` (expects UTF-8)
- For each column computes:
    - total rows
    - missing count and %
    - number of unique values
    - sample of most common values (top 10)
    - average string length (for textual columns)
- Writes a simple text summary to stdout and `audit_summary.txt` in the same folder as the CSV.

This helps decide which fields to stop scraping (high missing%, low variance, or not useful).
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


def analyze_csv(path, sample_limit=10):
    path = Path(path)
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        total = 0

        # Collect stats
        missing = Counter()
        uniques = defaultdict(Counter)  # field -> Counter of values
        lengths = defaultdict(int)      # field -> total chars

        for row in reader:
            total += 1
            for field in fieldnames:
                val = row.get(field, None)
                if val is None or val.strip() == '' or val == 'N/A':
                    missing[field] += 1
                else:
                    uniques[field][val] += 1
                    lengths[field] += len(val)

    # Build report
    lines = []
    lines.append("CSV Audit Report")
    lines.append("File: " + str(path))
    lines.append(f"Total rows: {total}\n")

    if total == 0:
        lines.append("No rows found in CSV.")
    else:
        header = f"{'Field':35} | {'Missing':8} | {'% Missing':9} | {'Unique':6} | {'AvgLen':6} | Top values"
        lines.append(header)
        lines.append('-' * len(header))

        for field in fieldnames:
            miss = missing.get(field, 0)
            miss_pct = (miss / total) * 100
            uniq_count = len(uniques[field])
            avg_len = (lengths[field] / (total - miss)) if (total - miss) > 0 else 0
            top_vals = uniques[field].most_common(sample_limit)
            top_preview = ', '.join([f"{v} ({c})" for v, c in top_vals[:5]])
            lines.append(f"{field:35} | {miss:8d} | {miss_pct:8.1f}% | {uniq_count:6d} | {avg_len:6.1f} | {top_preview}")

    report = '\n'.join(lines)
    print(report)

    # Write summary next to csv
    out_file = path.parent / (path.stem + '_audit_summary.txt')
    with out_file.open('w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nAudit summary written to: {out_file}")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python audit_scrape_results.py path/to/kbid_auctions_data.csv")
        sys.exit(2)
    csv_path = sys.argv[1]
    sys.exit(analyze_csv(csv_path))
