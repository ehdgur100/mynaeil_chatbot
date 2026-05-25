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
REFERER_URL = f"{BASE_URL}/in_appList.do?rcrtSeUrl=IN47002&bizSeUrl=IN49009"

STATUS_APPLYING = "IN17003"
RECRUIT_TYPE_INDIVIDUAL = "IN47002"
BUSINESS_TYPE_EDUCATION = "IN49009"

DEFAULT_OUTPUT_DIR = Path("data/50plus_education_applying")


def disable_proxy_env() -> None:
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
    disable_proxy_env()
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


def request_page(session: requests.Session, page: int) -> dict[str, Any]:
    data = {
        "ANN_NO": "",
        "pageIndex": str(page),
        "SRCH_BIZ_SE": BUSINESS_TYPE_EDUCATION,
        "bizSeUrl": BUSINESS_TYPE_EDUCATION,
        "SRCH_RCRT_SE_CD": RECRUIT_TYPE_INDIVIDUAL,
        "rcrtSeUrl": RECRUIT_TYPE_INDIVIDUAL,
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


def normalize_training(row: dict[str, Any]) -> dict[str, Any]:
    ann_no = row.get("ANN_NO")
    view_url = f"{BASE_URL}/in_appView.do?ANN_NO={ann_no}" if ann_no else None
    return {
        "ann_no": ann_no,
        "category": "취업훈련",
        "recruitment_status": "모집중",
        "title": row.get("ANN_NM"),
        "provider": row.get("CORPR_ORG"),
        "business_type_code": row.get("BIZ_SE"),
        "business_type_name": row.get("BIZ_SE_NM"),
        "recruit_status_code": row.get("ANN_RCRT_STAT"),
        "recruit_status_name": row.get("ANN_RCRT_STAT_NM"),
        "recruit_type_code": row.get("RCRT_SE_CD"),
        "recruit_type_name": row.get("RCRT_SE_NM"),
        "apply_period": row.get("APPDURNG_STED"),
        "apply_start": row.get("APPDURNG_STTM"),
        "apply_end": row.get("APPDURNG_EDTM"),
        "selection_announcement": row.get("PASS_DAY"),
        "dday": row.get("DDAY"),
        "recruit_count": row.get("RCRT_PPL"),
        "occupation_code": row.get("OCCUPATION"),
        "occupation_name": row.get("OCCUPATION_LABEL"),
        "work_condition_code": row.get("WORK_CONDITION"),
        "work_condition_name": row.get("WORK_CONDITION_LABEL"),
        "career_code": row.get("CAREER_HISTORY"),
        "career_name": row.get("CAREER_HISTORY_LABEL"),
        "fee_amount": row.get("ACTAMT_HAMT"),
        "fee_text": row.get("ACTAMT_PAMT"),
        "education_start": row.get("EVENT_DATE_START") or row.get("EDUDRNG_ST"),
        "education_end": row.get("EVENT_DATE_END") or row.get("EDUDRNG_ED"),
        "education_location": row.get("EVENT_LOCATION"),
        "pre_edu_yn": row.get("PRE_EDU_YN"),
        "application_url": view_url,
        "source_url": view_url,
        "crawled_at": datetime.now().isoformat(timespec="seconds"),
        "raw_data": row,
    }


def crawl_trainings(limit: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = make_session()
    first_page = request_page(session, 1)
    pagination = first_page.get("paginationInfo", {})
    total_count = int(pagination.get("totalRecordCount") or 0)
    total_pages = int(pagination.get("totalPageCount") or 1)
    target_count = min(total_count, limit) if limit else total_count

    trainings: list[dict[str, Any]] = []
    for page in range(1, total_pages + 1):
        payload = first_page if page == 1 else request_page(session, page)
        for row in payload.get("list", []):
            trainings.append(normalize_training(row))
            if len(trainings) >= target_count:
                return trainings, pagination
        print(f"Fetched {len(trainings):>3}/{target_count} rows")

    return trainings, pagination


def save_outputs(trainings: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "50plus_education_applying.csv"
    json_path = output_dir / "50plus_education_applying.json"

    flat_fields = [key for key in trainings[0].keys() if key != "raw_data"] if trainings else []
    with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=flat_fields)
        writer.writeheader()
        for training in trainings:
            writer.writerow({key: training.get(key) for key in flat_fields})

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(trainings, json_file, ensure_ascii=False, indent=2)

    return csv_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl applying 50plus education trainings from in_appListAjax."
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to save.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    try:
        trainings, pagination = crawl_trainings(args.limit)
        csv_path, json_path = save_outputs(trainings, args.output_dir)
        print(f"Site totalRecordCount: {pagination.get('totalRecordCount')}")
        print(f"Saved {len(trainings)} rows")
        print(f"CSV UTF-8: {csv_path}")
        print(f"JSON UTF-8: {json_path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
