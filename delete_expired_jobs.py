from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from typing import Any

from database.connection import supabase


BATCH_SIZE = 1000

TABLE_CONFIGS = {
    "jobs": {
        "select": "id,title,deadline,content",
        "date_fields": ("deadline",),
        "content_field": "content",
    },
    "jobs3": {
        "select": "id,title,deadline,content",
        "date_fields": ("deadline",),
        "content_field": "content",
    },
    "job_seoul_50": {
        "select": "id,title,recruit_status_name,apply_end,event_date_end",
        "date_fields": ("apply_end", "event_date_end"),
        "content_field": None,
    },
}


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y%m%d%H",
        "%Y%m%d",
        "%y/%m/%d",
        "%y.%m.%d",
    ):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue

    match = re.search(r"(20\d{2})[-./년\s]*(\d{1,2})[-./월\s]*(\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    match = re.search(r"(?<!\d)(\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(2000 + year, month, day)
        except ValueError:
            return None

    return None


def parse_deadline_from_content(content: Any) -> date | None:
    text = str(content or "")
    if not text:
        return None

    patterns = [
        r"마감일\s*\((20\d{2}[-./]\d{1,2}[-./]\d{1,2})\)",
        r"접수마감일[^\d]*(20\d{2}[-./]\d{1,2}[-./]\d{1,2})",
        r"등록/마감일[^\n\r]*?(\d{2}[./]\d{1,2}[./]\d{1,2})\s*마감",
        r"(\d{2}[./]\d{1,2}[./]\d{1,2})\s*마감",
        r"(20\d{2}[-./]\d{1,2}[-./]\d{1,2})\s*마감",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed
    return None


def fetch_rows(table: str, select_columns: str) -> list[dict[str, Any]]:
    if supabase is None:
        raise RuntimeError("Supabase client is not configured.")

    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + BATCH_SIZE - 1
        result = supabase.table(table).select(select_columns).range(start, end).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < BATCH_SIZE:
            break
        start += BATCH_SIZE
    return rows


def chunked(values: list[int], size: int = 100) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def row_deadline(row: dict[str, Any], config: dict[str, Any]) -> date | None:
    for field in config["date_fields"]:
        parsed = parse_date(row.get(field))
        if parsed:
            return parsed

    content_field = config.get("content_field")
    if content_field:
        return parse_deadline_from_content(row.get(content_field))
    return None


def is_closed_50plus(row: dict[str, Any]) -> bool:
    status = str(row.get("recruit_status_name") or "")
    return "마감" in status


def delete_expired(table: str, today: date, dry_run: bool) -> int:
    config = TABLE_CONFIGS[table]
    rows = fetch_rows(table, config["select"])
    expired: list[dict[str, Any]] = []

    for row in rows:
        deadline = row_deadline(row, config)
        if deadline is not None and deadline < today:
            expired.append(row)
            continue
        if table == "job_seoul_50" and is_closed_50plus(row):
            expired.append(row)

    expired_ids = [int(row["id"]) for row in expired if row.get("id") is not None]

    print(f"{table}: total_rows={len(rows)}, expired_rows={len(expired_ids)}")
    if dry_run or not expired_ids:
        return len(expired_ids)

    for id_batch in chunked(expired_ids):
        supabase.table(table).delete().in_("id", id_batch).execute()

    return len(expired_ids)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete expired job rows from jobs, jobs3, and job_seoul_50."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = date.today()
    print(f"today={today.isoformat()}")

    total_deleted = 0
    for table in TABLE_CONFIGS:
        total_deleted += delete_expired(table, today, args.dry_run)

    action = "would_delete_rows" if args.dry_run else "deleted_rows"
    print(f"{action}={total_deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
