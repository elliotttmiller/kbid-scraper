from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse

from .models import AuctionItem


CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MONEY_CHARS = re.compile(r"[^0-9.\-]")


def clean_text(value: object, maximum: int = 10_000) -> str:
    text = CONTROL_CHARS.sub("", str(value or "")).strip()
    return text[:maximum]


def parse_money(value: object) -> float:
    text = MONEY_CHARS.sub("", str(value or "0"))
    if text in {"", ".", "-", "-."}:
        return 0.0
    result = float(text)
    if result < 0 or result > 10_000_000:
        raise ValueError(f"invalid monetary value: {value!r}")
    return round(result, 2)


def parse_optional_float(value: object) -> float | None:
    text = clean_text(value)
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_time_remaining_minutes(value: object) -> float | None:
    text = clean_text(value).lower()
    if not text or text in {"unknown", "n/a"}:
        return None
    if text == "closed":
        return 0.0
    units = {"d": 1_440, "h": 60, "m": 1}
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*([dhm])\b", text)
    return sum(float(amount) * units[unit] for amount, unit in matches) if matches else None


def parse_optional_rate(value: object) -> float | None:
    text = clean_text(value)
    if not text or text.upper() == "N/A":
        return None
    is_percent = "%" in text
    try:
        rate = float(MONEY_CHARS.sub("", text))
    except ValueError:
        return None
    if is_percent or rate >= 1:
        rate /= 100
    return rate if 0 <= rate < 1 else None


def parse_optional_money(value: object) -> float | None:
    text = clean_text(value)
    if not text or text.upper() == "N/A":
        return None
    try:
        return parse_money(text)
    except ValueError:
        return None


def safe_url(value: object) -> str:
    text = clean_text(value, 2_048)
    if not text or text.upper() == "N/A":
        return ""
    parsed = urlparse(text)
    return text if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def row_to_item(row: Mapping[str, object]) -> AuctionItem:
    lot_number = clean_text(row.get("lot_number"), 100)
    auction_id = clean_text(row.get("auction_id"), 100)
    item_url = safe_url(row.get("item_url"))
    identity = item_url or f"{auction_id}:{lot_number}:{clean_text(row.get('item_title'), 300)}"
    item_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    category_ids = tuple(
        part.strip()
        for part in re.split(r"[,;>|]", clean_text(row.get("category_ids"), 1_000))
        if part.strip().isdigit()
    )
    quantity_text = clean_text(row.get("quantity"), 20)
    quantity = int(quantity_text) if quantity_text.isdigit() and int(quantity_text) > 0 else 1
    return AuctionItem(
        item_id=item_id,
        external_id=clean_text(row.get("id"), 200) or item_id,
        lot_number=lot_number,
        title=clean_text(row.get("item_title") or row.get("title"), 500),
        auction_title=clean_text(row.get("auction_title") or row.get("groupName"), 500),
        current_bid=parse_money(row.get("current_bid") or row.get("currentBid")),
        buyers_premium_rate=parse_optional_rate(row.get("buyers_premium_rate")),
        buyers_premium_cap=parse_optional_money(row.get("buyers_premium_cap")),
        sales_tax_rate=parse_optional_rate(row.get("sales_tax_rate")),
        category=clean_text(row.get("category"), 500) or "Uncategorized",
        category_ids=category_ids,
        description=clean_text(row.get("short_description") or row.get("description")),
        condition=clean_text(row.get("condition"), 100) or "Unknown",
        quantity=quantity,
        item_url=item_url,
        auction_url=safe_url(row.get("auction_url")),
        auction_id=auction_id,
        image_url=safe_url(row.get("image_url") or row.get("imageUrl")),
        location=clean_text(row.get("location"), 500),
        item_closing_time=clean_text(row.get("item_closing_time") or row.get("lot_closing_time"), 200),
        minutes_until_close=(
            parse_optional_float(row.get("minutes_until_close"))
            if clean_text(row.get("minutes_until_close"))
            else parse_time_remaining_minutes(row.get("time_remaining"))
        ),
        closing_status=clean_text(row.get("closing_status"), 100),
        prior_expected_profit=parse_optional_float(row.get("expected_profit")),
        prior_expected_sell_price=parse_optional_float(row.get("expected_sell_price")),
        prior_expected_roi=parse_optional_float(row.get("expected_roi_percent")),
        prior_maximum_bid=parse_optional_float(row.get("maximum_bid")),
        prior_market_confidence=parse_optional_float(row.get("market_confidence")),
        prior_verified_sold_count=int(parse_optional_float(row.get("verified_sold_comp_count")) or 0),
        prior_active_listing_count=int(parse_optional_float(row.get("active_listing_comp_count")) or 0),
        prior_active_listing_median=parse_optional_float(row.get("active_listing_median_price")),
    )


def load_items(path: str | Path, include_closed: bool = False) -> tuple[list[AuctionItem], list[str]]:
    items: list[AuctionItem] = []
    errors: list[str] = []
    seen: set[str] = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"lot_number", "item_title", "current_bid"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"input CSV missing required columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            try:
                item = row_to_item(row)
                status = item.closing_status.lower()
                expired = item.minutes_until_close is not None and item.minutes_until_close <= 0
                closed = any(term in status for term in ("closed", "complete", "ended"))
                if not include_closed and (expired or closed):
                    continue
                if not item.title:
                    raise ValueError("empty item title")
                if item.item_id in seen:
                    continue
                seen.add(item.item_id)
                items.append(item)
            except (TypeError, ValueError) as exc:
                errors.append(f"line {line_number}: {exc}")
    return items, errors


def items_from_payload(rows: Iterable[Mapping[str, object]]) -> list[AuctionItem]:
    return [row_to_item(row) for row in rows]
