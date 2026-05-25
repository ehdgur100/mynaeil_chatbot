import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client


load_dotenv(override=True)

for proxy_env_name in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(proxy_env_name, None)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TABLE_NAME = "education"


def clean(value: Any) -> Any:
    if value in ("", "nan", "NaN"):
        return None
    return value


def infer_category(row: dict[str, Any]) -> str | None:
    category = clean(row.get("category"))
    if category:
        return category

    source_url = clean(row.get("application_url") or row.get("source_url")) or ""
    business_type_code = clean(row.get("business_type_code"))
    business_type_name = clean(row.get("business_type_name"))

    if business_type_code == "AI_DIGITAL" or "educationKind=aiDigital" in source_url:
        return "AI디지털교육"
    if business_type_code == "CENTER_EDUCATION" or "educationKind=centerEducation" in source_url:
        return "50플러스센터교육"
    if business_type_code == "IN49009" or business_type_name == "직업훈련" or "in_appView.do" in source_url:
        return "취업훈련"
    return None


def infer_recruitment_status(row: dict[str, Any]) -> str | None:
    value = clean(row.get("recruitment_status"))
    if value in ("모집중", "모집예정", "모집마감"):
        return value

    status_name = clean(row.get("recruit_status_name"))
    status_code = clean(row.get("recruit_status_code"))

    if status_name in ("모집중", "신청·접수중", "신청ㆍ접수중"):
        return "모집중"
    if status_name == "모집예정":
        return "모집예정"
    if status_name in ("모집마감", "마감"):
        return "모집마감"
    if status_code in ("PENDING", "PEND"):
        return "모집예정"
    if status_code in ("OPEN", "WAITING", "IN17003"):
        return "모집중"
    if status_code in ("CLOSED", "CLOSE"):
        return "모집마감"
    return None


def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_rows(client: Client, page_size: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        result = (
            client.table(TABLE_NAME)
            .select(
                "id,category,recruitment_status,application_url,source_url,"
                "business_type_code,business_type_name,recruit_status_code,recruit_status_name"
            )
            .range(start, end)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        start += page_size


def backfill(client: Client, rows: list[dict[str, Any]], dry_run: bool) -> int:
    updated = 0
    for row in rows:
        application_url = clean(row.get("application_url") or row.get("source_url"))
        category = infer_category(row)
        recruitment_status = infer_recruitment_status(row)

        patch = {
            "application_url": application_url,
            "category": category,
            "recruitment_status": recruitment_status,
        }
        patch = {key: value for key, value in patch.items() if value is not None}

        needs_update = any(row.get(key) != value for key, value in patch.items())
        if not needs_update:
            continue

        patch["synced_at"] = datetime.now(timezone.utc).isoformat()
        updated += 1
        if dry_run:
            print(f"Would update id={row['id']}: {patch}")
            continue

        client.table(TABLE_NAME).update(patch).eq("id", row["id"]).execute()
        print(f"Updated id={row['id']}: {patch}")

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill category, recruitment_status, and application_url in education."
    )
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        client = get_supabase()
        rows = fetch_rows(client, args.page_size)
        count = backfill(client, rows, args.dry_run)
        action = "Would update" if args.dry_run else "Updated"
        print(f"{action} {count}/{len(rows)} rows.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
