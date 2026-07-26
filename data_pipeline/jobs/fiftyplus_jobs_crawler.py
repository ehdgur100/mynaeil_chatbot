import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://www.50plus.or.kr"
LIST_URL = f"{BASE_URL}/in_appListAjax"
REFERER_URL = f"{BASE_URL}/in_appList.do?rcrtSeUrl=IN47002"

STATUS_APPLYING = "IN17003"
RECRUIT_TYPE_JOB = "IN47002"


def disable_dead_proxy_env() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)


def make_session() -> requests.Session:
    disable_dead_proxy_env()
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "Referer": REFERER_URL,
        }
    )
    return session


def request_page(session: requests.Session, page: int, biz_se: str | None) -> dict[str, Any]:
    data = {
        "ANN_NO": "",
        "pageIndex": str(page),
        "SRCH_BIZ_SE": biz_se or "",
        "bizSeUrl": biz_se or "",
        "SRCH_RCRT_SE_CD": RECRUIT_TYPE_JOB,
        "rcrtSeUrl": RECRUIT_TYPE_JOB,
        "orgCd": "jpp",
        "SRCH_OCCUPATION_LIST": "",
        "SRCH_WORK_CONDITION_LIST": "",
        "SRCH_CAREER_HISTORY_LIST": "",
        "SRCH_WORK_LOCATION_LIST": "",
        "SRCH_BIZ_SE_NM": "",
        "SRCH_ANN_RCRT_STAT": STATUS_APPLYING,
        "PRE_EDU_YN": "",
        "SRCH_OPER_ORG": "",
        "SRCH_KWD_VAL": "",
    }
    response = session.post(LIST_URL, data=data, timeout=30)
    response.raise_for_status()
    return json.loads(response.content.decode("utf-8"))


def crawl_jobs(limit: int | None, biz_se: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = make_session()
    first_page = request_page(session, 1, biz_se)
    pagination = first_page.get("paginationInfo", {})
    total_count = int(pagination.get("totalRecordCount") or 0)
    total_pages = int(pagination.get("totalPageCount") or 1)

    target_count = min(total_count, limit) if limit else total_count
    jobs: list[dict[str, Any]] = []
    
    # Get today's date string in YYYYMMDD format
    today_str = datetime.now().strftime("%Y%m%d")

    for page in range(1, total_pages + 1):
        payload = first_page if page == 1 else request_page(session, page, biz_se)
        for row in payload.get("list", []):
            apply_end = row.get("APPDURNG_EDTM", "")
            
            # Check if apply_end date is before today
            if apply_end and len(apply_end) >= 8:
                end_date_str = apply_end[:8]
                if end_date_str < today_str:
                    continue  # Skip jobs with past deadlines
            
            jobs.append(normalize_job(row))
            if len(jobs) >= target_count:
                return jobs, pagination
        print(f"Fetched {len(jobs):>3} valid rows from page {page}")

    return jobs, pagination


def normalize_job(row: dict[str, Any]) -> dict[str, Any]:
    ann_no = row.get("ANN_NO")
    view_url = f"{BASE_URL}/in_appView.do?ANN_NO={ann_no}" if ann_no else ""
    return {
        "ann_no": ann_no,
        "title": row.get("ANN_NM"),
        "company_or_org": row.get("CORPR_ORG"),
        "business_type_code": row.get("BIZ_SE"),
        "business_type_name": row.get("BIZ_SE_NM"),
        "recruit_status_code": row.get("ANN_RCRT_STAT"),
        "recruit_status_name": row.get("ANN_RCRT_STAT_NM"),
        "recruit_type_code": row.get("RCRT_SE_CD"),
        "recruit_type_name": row.get("RCRT_SE_NM"),
        "apply_period": row.get("APPDURNG_STED"),
        "apply_start": row.get("APPDURNG_STTM"),
        "apply_end": row.get("APPDURNG_EDTM"),
        "dday": row.get("DDAY"),
        "recruit_count": row.get("RCRT_PPL"),
        "occupation_code": row.get("OCCUPATION"),
        "occupation_name": row.get("OCCUPATION_LABEL"),
        "work_condition_code": row.get("WORK_CONDITION"),
        "work_condition_name": row.get("WORK_CONDITION_LABEL"),
        "career_code": row.get("CAREER_HISTORY"),
        "career_name": row.get("CAREER_HISTORY_LABEL"),
        "pay_hourly": row.get("ACTAMT_HAMT"),
        "pay_text": row.get("ACTAMT_PAMT"),
        "event_date_start": row.get("EVENT_DATE_START"),
        "event_date_end": row.get("EVENT_DATE_END"),
        "event_location": row.get("EVENT_LOCATION"),
        "pre_edu_yn": row.get("PRE_EDU_YN"),
        "source_url": view_url,
        "crawled_at": datetime.now().isoformat(timespec="seconds"),
        "raw_data": row,
    }


def save_outputs(jobs: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "50plus_jobs_applying.csv"
    json_path = output_dir / "50plus_jobs_applying.json"

    flat_fields = [key for key in jobs[0].keys() if key != "raw_data"] if jobs else []
    with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=flat_fields)
        writer.writeheader()
        for job in jobs:
            writer.writerow({key: job.get(key) for key in flat_fields})

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(jobs, json_file, ensure_ascii=False, indent=2)

    return csv_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl 50plus applying job posts from in_appListAjax."
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to save.")
    parser.add_argument(
        "--biz-se",
        default=None,
        help="Optional BIZ_SE filter. Use IN49008 for only the site category named 민간채용공고.",
    )
    parser.add_argument("--output-dir", default="data", help="Output directory.")
    args = parser.parse_args()

    try:
        jobs, pagination = crawl_jobs(args.limit, args.biz_se)
        csv_path, json_path = save_outputs(jobs, Path(args.output_dir))
        print(f"Site totalRecordCount: {pagination.get('totalRecordCount')}")
        print(f"Saved {len(jobs)} rows")
        print(f"CSV UTF-8: {csv_path}")
        print(f"JSON UTF-8: {json_path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
