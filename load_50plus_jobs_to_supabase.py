import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from postgrest.exceptions import APIError
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
TABLE_NAME = "job_seoul_50"
DEFAULT_JSON_PATH = Path("data/50plus_private_applying/50plus_jobs_applying.json")


def clean_value(value: Any) -> Any:
    if value in ("", "nan", "NaN"):
        return None
    return value


def to_int(value: Any) -> int | None:
    value = clean_value(value)
    if value is None:
        return None
    return int(float(value))


def to_float(value: Any) -> float | None:
    value = clean_value(value)
    if value is None:
        return None
    return float(value)


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ann_no": to_int(row.get("ann_no")),
        "title": clean_value(row.get("title")),
        "company_or_org": clean_value(row.get("company_or_org")),
        "recruit_status_name": clean_value(row.get("recruit_status_name")),
        "apply_period": clean_value(row.get("apply_period")),
        "apply_start": clean_value(row.get("apply_start")),
        "apply_end": clean_value(row.get("apply_end")),
        "dday": to_int(row.get("dday")),
        "recruit_count": to_int(row.get("recruit_count")),
        "occupation_name": clean_value(row.get("occupation_name")),
        "work_condition_name": clean_value(row.get("work_condition_name")),
        "career_code": clean_value(row.get("career_code")),
        "career_name": clean_value(row.get("career_name")),
        "pay_hourly": to_float(row.get("pay_hourly")),
        "pay_text": clean_value(row.get("pay_text")),
        "event_date_start": clean_value(row.get("event_date_start")),
        "event_date_end": clean_value(row.get("event_date_end")),
        "event_location": clean_value(row.get("event_location")),
        "pre_edu_yn": clean_value(row.get("pre_edu_yn")),
        "source_url": clean_value(row.get("source_url")),
        "raw_data": row.get("raw_data") or {},
    }


def load_jobs(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        raise RuntimeError(f"Input JSON not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as file:
        rows = json.load(file)

    return [normalize_row(row) for row in rows]


def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_jobs(client: Client, jobs: list[dict[str, Any]], batch_size: int) -> None:
    for idx in range(0, len(jobs), batch_size):
        batch = jobs[idx : idx + batch_size]
        try:
            client.table(TABLE_NAME).upsert(batch, on_conflict="ann_no").execute()
        except APIError as exc:
            message = str(exc)
            if "PGRST205" in message or f"'{TABLE_NAME}'" in message:
                raise RuntimeError(
                    f"Supabase table '{TABLE_NAME}' does not exist yet. "
                    "Run sql/create_job_seoul_50.sql in the Supabase SQL Editor first."
                ) from exc
            if "row-level security" in message or "42501" in message:
                raise RuntimeError(
                    f"Supabase row-level security is blocking writes to '{TABLE_NAME}'. "
                    "Run sql/create_job_seoul_50.sql again, or disable RLS/add an insert policy."
                ) from exc
            raise
        print(f"Upserted {min(idx + len(batch), len(jobs)):>3}/{len(jobs)} rows")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load 50plus applying jobs into Supabase.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    try:
        jobs = load_jobs(args.json_path)
        if not jobs:
            print("No rows to upload.")
            return 0

        client = get_supabase()
        upsert_jobs(client, jobs, args.batch_size)
        print(f"Done. {len(jobs)} rows synced into {TABLE_NAME}.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
