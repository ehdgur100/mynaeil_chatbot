from __future__ import annotations

from datetime import date, datetime
from typing import Any

from database.connection import supabase


TODAY = date.today()
BATCH_SIZE = 1000


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d%H", "%Y%m%d", "%y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def fetch_rows() -> list[dict[str, Any]]:
    if supabase is None:
        raise RuntimeError("Supabase client is not configured.")

    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + BATCH_SIZE - 1
        result = (
            supabase.table("education")
            .select("id,title,category,recruitment_status,apply_end,application_url")
            .range(start, end)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < BATCH_SIZE:
            break
        start += BATCH_SIZE
    return rows


def chunked(values: list[int], size: int = 100) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def main() -> None:
    rows = fetch_rows()
    expired = [
        row
        for row in rows
        if (apply_end := parse_date(row.get("apply_end"))) is not None
        and apply_end < TODAY
    ]
    expired_ids = [int(row["id"]) for row in expired if row.get("id") is not None]

    print(f"today={TODAY.isoformat()}")
    print(f"total_rows={len(rows)}")
    print(f"expired_rows={len(expired_ids)}")

    if not expired_ids:
        print("No expired education rows to delete.")
        return

    for id_batch in chunked(expired_ids):
        supabase.table("education").delete().in_("id", id_batch).execute()

    print(f"deleted_rows={len(expired_ids)}")


if __name__ == "__main__":
    main()
