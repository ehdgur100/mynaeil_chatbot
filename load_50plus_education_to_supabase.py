import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))

TABLE_NAME = "education"
DEFAULT_JSON_PATH = Path("data/50plus_education_applying/50plus_education_applying.json")


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


def infer_category(row: dict[str, Any]) -> str | None:
    value = clean_value(row.get("category"))
    if value:
        return value

    application_url = clean_value(row.get("application_url") or row.get("source_url")) or ""
    business_type_code = clean_value(row.get("business_type_code"))
    business_type_name = clean_value(row.get("business_type_name"))

    if business_type_code == "AI_DIGITAL" or "educationKind=aiDigital" in application_url:
        return "AI디지털교육"
    if business_type_code == "CENTER_EDUCATION" or "educationKind=centerEducation" in application_url:
        return "50플러스센터교육"
    if business_type_code == "IN49009" or business_type_name == "직업훈련" or "in_appView.do" in application_url:
        return "취업훈련"
    return None


def normalize_recruitment_status(row: dict[str, Any]) -> str | None:
    value = clean_value(row.get("recruitment_status"))
    if value in ("모집중", "모집예정", "모집마감"):
        return value

    status_name = clean_value(row.get("recruit_status_name"))
    status_code = clean_value(row.get("recruit_status_code"))

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


def build_content(row: dict[str, Any]) -> str:
    parts = [
        f"교육명: {row.get('title')}",
        f"교육종류: {row.get('category')}",
        f"운영기관: {row.get('provider')}",
        f"분류: {row.get('business_type_name')}",
        f"교육기수: {row.get('term')}",
        f"강사: {row.get('lecturer') or row.get('main_lecturer')}",
        f"모집상태: {row.get('recruitment_status') or row.get('recruit_status_name')}",
        f"신청기간: {row.get('apply_period')}",
        f"교육기간: {row.get('education_start')}~{row.get('education_end')}",
        f"교육장소: {row.get('education_location')}",
        f"모집인원: {row.get('recruit_count')}",
        f"교육분야: {row.get('occupation_name')}",
        f"경력조건: {row.get('career_name')}",
        f"교육비: {row.get('fee_text') or row.get('fee_amount')}",
    ]
    return "\n".join(part for part in parts if part and not part.endswith(": None"))


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    application_url = clean_value(row.get("application_url") or row.get("source_url"))
    if not application_url:
        raise ValueError(f"application_url is required for upsert: {row.get('title')}")

    normalized = {
        "ann_no": to_int(row.get("ann_no")),
        "category": infer_category(row),
        "recruitment_status": normalize_recruitment_status(row),
        "title": clean_value(row.get("title")),
        "provider": clean_value(row.get("provider")),
        "business_type_code": clean_value(row.get("business_type_code")),
        "business_type_name": clean_value(row.get("business_type_name")),
        "recruit_status_code": clean_value(row.get("recruit_status_code")),
        "recruit_status_name": clean_value(row.get("recruit_status_name")),
        "recruit_type_code": clean_value(row.get("recruit_type_code")),
        "recruit_type_name": clean_value(row.get("recruit_type_name")),
        "apply_period": clean_value(row.get("apply_period")),
        "apply_start": clean_value(row.get("apply_start")),
        "apply_end": clean_value(row.get("apply_end")),
        "selection_announcement": clean_value(row.get("selection_announcement")),
        "dday": to_int(row.get("dday")),
        "recruit_count": to_int(row.get("recruit_count")),
        "occupation_code": clean_value(row.get("occupation_code")),
        "occupation_name": clean_value(row.get("occupation_name")),
        "work_condition_code": clean_value(row.get("work_condition_code")),
        "work_condition_name": clean_value(row.get("work_condition_name")),
        "career_code": clean_value(row.get("career_code")),
        "career_name": clean_value(row.get("career_name")),
        "fee_amount": to_float(row.get("fee_amount")),
        "fee_text": clean_value(row.get("fee_text")),
        "education_start": clean_value(row.get("education_start")),
        "education_end": clean_value(row.get("education_end")),
        "education_location": clean_value(row.get("education_location")),
        "pre_edu_yn": clean_value(row.get("pre_edu_yn")),
        "application_url": application_url,
        "source_url": clean_value(row.get("source_url") or application_url),
        "crawled_at": clean_value(row.get("crawled_at")),
        "raw_data": row.get("raw_data") or {},
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    normalized["content"] = build_content({**row, **normalized})
    return normalized


def load_trainings(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        raise RuntimeError(f"Input JSON not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as file:
        rows = json.load(file)

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        normalized = normalize_row(row)
        deduped[normalized["application_url"]] = normalized
    return list(deduped.values())


def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def ensure_table_access(client: Client) -> None:
    try:
        client.table(TABLE_NAME).select("application_url").limit(1).execute()
    except APIError as exc:
        message = str(exc)
        if "PGRST205" in message or f"'{TABLE_NAME}'" in message:
            raise RuntimeError(
                f"Supabase table '{TABLE_NAME}' does not exist yet. "
                "Run sql/create_education.sql in the Supabase SQL Editor first."
            ) from exc
        if "application_url" in message or "PGRST204" in message:
            raise RuntimeError(
                "Supabase table 'education' is missing the application_url/category columns. "
                "Run the updated sql/create_education.sql in the Supabase SQL Editor first."
            ) from exc
        if "row-level security" in message or "42501" in message:
            raise RuntimeError(
                f"Supabase row-level security is blocking reads from '{TABLE_NAME}'. "
                "Run sql/create_education.sql again, or disable RLS/add a select policy."
            ) from exc
        raise


def embed_contents(rows: list[dict[str, Any]], batch_size: int) -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY must be set in .env to create embeddings")

    client = OpenAI(api_key=OPENAI_API_KEY)
    for idx in range(0, len(rows), batch_size):
        batch = rows[idx : idx + batch_size]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[row["content"] for row in batch],
            dimensions=EMBEDDING_DIMENSIONS,
        )
        for row, item in zip(batch, response.data):
            row["embedding"] = item.embedding
        print(f"Embedded {min(idx + len(batch), len(rows)):>3}/{len(rows)} rows")


def upsert_trainings(client: Client, rows: list[dict[str, Any]], batch_size: int) -> None:
    for idx in range(0, len(rows), batch_size):
        batch = rows[idx : idx + batch_size]
        try:
            client.table(TABLE_NAME).upsert(batch, on_conflict="application_url").execute()
        except APIError as exc:
            message = str(exc)
            if "PGRST205" in message or f"'{TABLE_NAME}'" in message:
                raise RuntimeError(
                    f"Supabase table '{TABLE_NAME}' does not exist yet. "
                    "Run sql/create_education.sql in the Supabase SQL Editor first."
                ) from exc
            if "application_url" in message or "42P10" in message:
                raise RuntimeError(
                    "Supabase table 'education' needs a unique index on application_url. "
                    "Run the updated sql/create_education.sql in the Supabase SQL Editor first."
                ) from exc
            if "row-level security" in message or "42501" in message:
                raise RuntimeError(
                    f"Supabase row-level security is blocking writes to '{TABLE_NAME}'. "
                    "Run sql/create_education.sql again, or disable RLS/add an insert policy."
                ) from exc
            raise
        print(f"Upserted {min(idx + len(batch), len(rows)):>3}/{len(rows)} rows")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load 50plus education rows into Supabase with embeddings."
    )
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Upload rows without generating embedding vectors.",
    )
    args = parser.parse_args()

    try:
        rows = load_trainings(args.json_path)
        if not rows:
            print("No rows to upload.")
            return 0

        client = get_supabase()
        ensure_table_access(client)

        if not args.skip_embeddings:
            embed_contents(rows, args.batch_size)

        upsert_trainings(client, rows, args.batch_size)
        print(f"Done. {len(rows)} rows synced into {TABLE_NAME}.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
