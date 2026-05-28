from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from typing import Any

import requests

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

import config
from database.connection import supabase


API_URL_TEMPLATE = "http://openapi.seoul.go.kr:8088/{api_key}/json/GetJobInfo/{start}/{end}/"
BATCH_SIZE = 1000


for proxy_env_name in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(proxy_env_name, None)


def clean(value: Any) -> str:
    return str(value or "").strip()


def wanted_auth_no_from_url(url: str) -> str:
    for pattern in (r"wantedAuthNo=([^&\s]+)", r"/jobs3/wanted/([^/?#\s]+)", r"seoul_job_([^/?#\s]+)"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def deadline_date(value: Any) -> str | None:
    text = clean(value)
    match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def build_content(row: dict[str, Any]) -> str:
    fields = {
        "요약": row.get("GUI_LN"),
        "모집직종": row.get("JOBCODE_NM"),
        "모집인원": f"{row.get('RCRIT_NMPR_CO')}명" if row.get("RCRIT_NMPR_CO") else "",
        "담당업무": row.get("DTY_CN"),
        "지원자격": "\n".join(
            part
            for part in (
                f"학력: {clean(row.get('ACDMCR_NM')) or '관계없음'}",
                f"경력: {clean(row.get('CAREER_CND_NM')) or '관계없음'}",
            )
            if part
        ),
        "근무지역": row.get("WORK_PARAR_BASS_ADRES_CN"),
        "급여": row.get("HOPE_WAGE"),
        "고용형태": row.get("EMPLYM_STLE_CMMN_MM"),
        "근무시간": row.get("WORK_TIME_NM"),
        "근무조건": "\n".join(
            part
            for part in (
                f"근무형태: {clean(row.get('HOLIDAY_NM')) or '확인 필요'}",
                f"주 근로시간: {clean(row.get('WEEK_WORK_HR')) or '확인 필요'}",
            )
            if part
        ),
        "사회보험": row.get("JO_FEINSR_SBSCRB_NM"),
        "접수방법": row.get("RCEPT_MTH_NM"),
        "전형방법": row.get("MODEL_MTH_NM"),
        "제출서류": row.get("PRESENTN_PAPERS_NM"),
        "접수마감일": row.get("RCEPT_CLOS_NM"),
        "담당기관": row.get("MNGR_INSTT_NM"),
        "사업장주소": row.get("BASS_ADRES_CN"),
    }
    parts = [
        f"[{label}]\n{clean(value)}"
        for label, value in fields.items()
        if clean(value)
    ]
    return "\n\n".join(parts) if parts else "상세 내용 없음"


def fetch_api_rows(target_count: int) -> dict[str, dict[str, Any]]:
    api_key = config.SEOUL_JOB_API_KEY or "4d456c704c6b686a3132304b4f4c7a4c"
    session = requests.Session()
    session.trust_env = False

    rows_by_id: dict[str, dict[str, Any]] = {}
    start = 1
    while len(rows_by_id) < target_count:
        end = start + BATCH_SIZE - 1
        url = API_URL_TEMPLATE.format(api_key=api_key, start=start, end=end)
        response = session.get(url, timeout=30)
        data = response.json()
        rows = data.get("GetJobInfo", {}).get("row", [])
        if not rows:
            break
        for row in rows:
            wanted_auth_no = clean(row.get("JO_REQST_NO"))
            if wanted_auth_no:
                rows_by_id[wanted_auth_no] = row
        print(f"fetched_api_rows={len(rows_by_id)}")
        if len(rows) < BATCH_SIZE:
            break
        start = end + 1
    return rows_by_id


def fetch_jobs3_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + BATCH_SIZE - 1
        result = supabase.table("jobs3").select("id,url,external_id").range(start, end).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < BATCH_SIZE:
            break
        start += BATCH_SIZE
    return rows


def row_to_update(row: dict[str, Any], api_row: dict[str, Any], public_base_url: str) -> dict[str, Any]:
    wanted_auth_no = clean(api_row.get("JO_REQST_NO"))
    return {
        "title": clean(api_row.get("JO_SJ")) or "제목없음",
        "company": clean(api_row.get("CMPNY_NM")) or "기업명없음",
        "content": build_content(api_row),
        "url": f"{public_base_url}/jobs3/wanted/{wanted_auth_no}",
        "created_at": datetime.now().isoformat(),
        "external_id": wanted_auth_no,
        "location": clean(api_row.get("WORK_PARAR_BASS_ADRES_CN")),
        "salary": clean(api_row.get("HOPE_WAGE")),
        "career_required": clean(api_row.get("CAREER_CND_NM")),
        "employment_type": clean(api_row.get("EMPLYM_STLE_CMMN_MM")),
        "job_category": clean(api_row.get("JOBCODE_NM")),
        "deadline": deadline_date(api_row.get("RCEPT_CLOS_NM")),
        "apply_method": clean(api_row.get("RCEPT_MTH_NM")),
        "source": "서울시 일자리 API",
        "embedding": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill jobs3 URLs and detailed content from Seoul job API."
    )
    parser.add_argument("--target-count", type=int, default=5000)
    args = parser.parse_args()

    if supabase is None:
        raise RuntimeError("Supabase client is not configured.")

    public_base_url = config.PUBLIC_BASE_URL
    api_rows = fetch_api_rows(args.target_count)
    rows = fetch_jobs3_rows()
    updated = 0
    skipped = 0

    for row in rows:
        wanted_auth_no = clean(row.get("external_id")) or wanted_auth_no_from_url(clean(row.get("url")))
        api_row = api_rows.get(wanted_auth_no)
        if not api_row:
            skipped += 1
            continue
        supabase.table("jobs3").update(row_to_update(row, api_row, public_base_url)).eq(
            "id", row["id"]
        ).execute()
        updated += 1
        if updated % 100 == 0:
            print(f"updated={updated}, skipped={skipped}")

    print(f"done updated={updated}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
