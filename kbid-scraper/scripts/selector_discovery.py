"""
Lightweight selector discovery tool.
Scans one or more local HTML/text files and proposes CSS selectors for common auction fields.

Usage:
    python selector_discovery.py <file1> [file2 ...]

If no files provided, it will look for `bid-element.txt` in the repo root as a convenience.

Output: writes a JSON file under results/selector_suggestions_<timestamp>.json
"""
import sys
import os
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime

# Fields we care about
FIELDS = [
    'current_bid',
    'next_required_bid',
    'high_bidder',
    'item_title',
    'image_url',
    'item_closing_time',
    'lot_number'
]

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RESULTS_DIR = os.path.join(ROOT, 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)


def make_selector(el):
    """Generate a compact CSS selector for an element using id or classes when possible."""
    if not el or not getattr(el, 'name', None):
        return None
    # Prefer id
    eid = el.get('id')
    if eid:
        return f"#{eid}"
    classes = el.get('class') or []
    if classes:
        # pick up to 2 classes
        safe = [c for c in classes if re.match(r'^[A-Za-z0-9_\-]+$', c)]
        if safe:
            return f"{el.name}.{'.'.join(safe[:2])}"
    # fallback to tag and parent
    parent = el.parent
    if parent and getattr(parent, 'name', None):
        pclasses = parent.get('class') or []
        if pclasses:
            safe_p = [c for c in pclasses if re.match(r'^[A-Za-z0-9_\-]+$', c)]
            if safe_p:
                return f"{parent.name}.{safe_p[0]} > {el.name}"
    return el.name


def find_candidates(soup):
    """Scan the soup and return candidate selectors grouped by field."""
    candidates = {f: {} for f in FIELDS}

    text_all = soup.get_text(' ', strip=True)

    # current_bid: elements that contain $ sign
    for el in soup.find_all(string=re.compile(r'\$\s*\d')):
        parent = el if getattr(el, 'parent', None) else None
        sel = make_selector(parent)
        if sel:
            candidates['current_bid'].setdefault(sel, 0)
            candidates['current_bid'][sel] += 1

    # also look for classes/ids with 'current' and 'bid'
    for el in soup.find_all(attrs={'class': re.compile(r'current.*bid|lot-current-bid|current_bid', re.I)}):
        sel = make_selector(el)
        if sel:
            candidates['current_bid'].setdefault(sel, 0)
            candidates['current_bid'][sel] += 2
    for el in soup.find_all(attrs={'id': re.compile(r'lot_current_bid|lotCurrentBid|current_bid', re.I)}):
        sel = make_selector(el)
        if sel:
            candidates['current_bid'].setdefault(sel, 0)
            candidates['current_bid'][sel] += 3

    # next_required_bid: look for text 'Next Required Bid' and neighbours
    for node in soup.find_all(string=re.compile(r'Next Required Bid|Next Required|Next Bid', re.I)):
        parent = node.find_parent()
        if parent:
            # look for sibling nodes with $
            nxt = parent.find_next(string=re.compile(r'\$\s*\d'))
            if nxt:
                sel = make_selector(nxt.parent)
                if sel:
                    candidates['next_required_bid'].setdefault(sel, 0)
                    candidates['next_required_bid'][sel] += 2
            selp = make_selector(parent)
            if selp:
                candidates['next_required_bid'].setdefault(selp, 0)
                candidates['next_required_bid'][selp] += 1

    # high_bidder: look for label 'High Bidder' or patterns like '#1234'
    for node in soup.find_all(string=re.compile(r'High Bidder', re.I)):
        p = node.find_parent()
        if p:
            sel = make_selector(p)
            if sel:
                candidates['high_bidder'].setdefault(sel, 0)
                candidates['high_bidder'][sel] += 2
            # check next text for #123
            nxt = p.find_next(string=re.compile(r'#\d{3,8}'))
            if nxt:
                sel2 = make_selector(nxt.parent)
                if sel2:
                    candidates['high_bidder'].setdefault(sel2, 0)
                    candidates['high_bidder'][sel2] += 1

    # item_title: h1/h2/h3 with significant text
    for tag in ['h1', 'h2', 'h3']:
        for el in soup.find_all(tag):
            txt = el.get_text(strip=True)
            if txt and len(txt) > 10:
                sel = make_selector(el)
                candidates['item_title'].setdefault(sel, 0)
                candidates['item_title'][sel] += 2

    # image_url: og:image meta or img[src]
    meta = soup.find('meta', property='og:image')
    if meta and meta.get('content'):
        candidates['image_url'].setdefault('meta[property="og:image"]', 0)
        candidates['image_url']['meta[property="og:image"]'] += 3
    for img in soup.find_all('img', src=True):
        sel = make_selector(img)
        if sel:
            candidates['image_url'].setdefault(sel, 0)
            candidates['image_url'][sel] += 1

    # item_closing_time: look for 'Begins Closing' or 'Time Remaining'
    for node in soup.find_all(string=re.compile(r'Begins Closing|Time Remaining|Begins', re.I)):
        p = node.find_parent()
        if p:
            sel = make_selector(p)
            candidates['item_closing_time'].setdefault(sel, 0)
            candidates['item_closing_time'][sel] += 1

    # lot_number: look for 'Lot #' or 'Lot:'
    for node in soup.find_all(string=re.compile(r'Lot\s*#|Lot:\s*\d|Lot\s*:\s*\d', re.I)):
        p = node.find_parent()
        if p:
            sel = make_selector(p)
            candidates['lot_number'].setdefault(sel, 0)
            candidates['lot_number'][sel] += 2

    return candidates


def merge_counts(accum, new):
    for f, d in new.items():
        for sel, cnt in d.items():
            accum[f].setdefault(sel, 0)
            accum[f][sel] += cnt


def propose_selectors(files):
    accum = {f: {} for f in FIELDS}
    details = {}
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                txt = fh.read()
        except Exception:
            continue
        soup = BeautifulSoup(txt, 'html.parser')
        cand = find_candidates(soup)
        merge_counts(accum, cand)
        details[os.path.basename(fp)] = cand
    # for each field pick top 3 selectors by score
    suggestions = {}
    for f, d in accum.items():
        items = sorted(d.items(), key=lambda x: x[1], reverse=True)
        suggestions[f] = [ {'selector': sel, 'score': sc} for sel, sc in items[:5] ]
    return suggestions, details


def main():
    files = sys.argv[1:]
    if not files:
        # try convenience location
        default = os.path.abspath(os.path.join(ROOT, '..', 'bid-element.txt'))
        # also look for project-level bid-element.txt
        fallback = os.path.join(ROOT, 'bid-element.txt')
        candidates = []
        if os.path.exists(fallback):
            candidates.append(fallback)
        # look for a few common sample names
        sample = os.path.join(ROOT, 'kbid-scraper', 'bid-element.txt')
        if os.path.exists(sample):
            candidates.append(sample)
        # also look in repo root
        root_sample = os.path.join(ROOT, '..', 'bid-element.txt')
        if os.path.exists(root_sample):
            candidates.append(root_sample)
        # last resort: the single file in this repo we know
        pkg_sample = os.path.abspath(os.path.join(ROOT, '..', 'bid-element.txt'))
        if os.path.exists(pkg_sample):
            candidates.append(pkg_sample)
        # fall back to the file passed as absolute inside repo
        another = os.path.abspath(os.path.join(ROOT, '..', 'bid-element.txt'))
        if os.path.exists(another) and another not in candidates:
            candidates.append(another)
        # finally attempt to use a file in current working dir named bid-element.txt
        cwd = os.path.abspath('bid-element.txt')
        if os.path.exists(cwd):
            candidates.append(cwd)
        # also include the repository file provided by the user
        provided = os.path.abspath(os.path.join(ROOT, '..', 'kbid-scraper', 'bid-element.txt'))
        if os.path.exists(provided) and provided not in candidates:
            candidates.append(provided)
        # Also accept the copy in workspace root results if exists
        root2 = os.path.abspath(os.path.join(ROOT, '..', 'results'))
        if os.path.isdir(root2):
            # look for any txt/html under results
            for fn in os.listdir(root2):
                if fn.lower().endswith(('.html', '.htm', '.txt')):
                    candidates.append(os.path.join(root2, fn))
        if not candidates:
            print('No input files provided and no default sample found. Provide file paths.')
            return
        files = candidates

    suggestions, details = propose_selectors(files)
    out = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'files_processed': files,
        'suggestions': suggestions,
        'details': details
    }
    fname = os.path.join(RESULTS_DIR, f"selector_suggestions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fname, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f"Wrote selector suggestions to: {fname}")


if __name__ == '__main__':
    main()
