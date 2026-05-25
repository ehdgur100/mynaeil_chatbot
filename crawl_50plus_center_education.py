import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://www.50plus.or.kr"
LIST_URL = f"{BASE_URL}/api/lectures/list"
REFERER_URL_TEMPLATE = (
    f"{BASE_URL}/centerEducation.do?viewCount=12&state={{state}}&cost=ALL&term=undefined"
    "&type=ALL&orgCode=ALL"
)

DEFAULT_OUTPUT_DIR = Path("data/50plus_center_education_joining")
STATE_LABELS = {
    "JOIN": "모집중",
    "PEND": "모집예정",
    "CLOSE": "모집마감",
}
STATE_SLUGS = {
    "JOIN": "joining",
    "PEND": "pending",
    "CLOSE": "closed",
}


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


def make_session(state: str) -> requests.Session:
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
            "Referer": REFERER_URL_TEMPLATE.format(state=state),
        }
    )
    return session


def request_page(session: requests.Session, page: int, state: str) -> dict[str, Any]:
    params = {
        "educationKind": "centerEducation",
        "page": page,
        "state": state,
        "cost": "ALL",
        "type": "ALL",
        "orgCode": "ALL",
        "term": "",
    }
    response = session.get(LIST_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_yymmdd(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) != 6 or not text.isdigit():
        return text
    return f"20{text[:2]}-{text[2:4]}-{text[4:6]}"


def calculate_dday(end_date: str | None) -> int | None:
    if not end_date:
        return None
    try:
        target = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (target - date.today()).days


def normalize_lecture(row: dict[str, Any], state: str) -> dict[str, Any]:
    lecture_id = row.get("id")
    apply_start = parse_yymmdd(row.get("registStartDate"))
    apply_end = parse_yymmdd(row.get("registEndDate"))
    education_start = parse_yymmdd(row.get("courseStartDate"))
    education_end = parse_yymmdd(row.get("courseEndDate"))
    source_url = (
        f"{BASE_URL}/education-detail.do?id={lecture_id}&viewCount=12&educationKind=centerEducation"
        if lecture_id
        else None
    )

    return {
        "ann_no": lecture_id,
        "category": "50플러스센터교육",
        "recruitment_status": STATE_LABELS.get(state, state),
        "title": row.get("title"),
        "provider": row.get("orgName"),
        "business_type_code": "CENTER_EDUCATION",
        "business_type_name": "50플러스센터 교육",
        "recruit_status_code": row.get("status"),
        "recruit_status_name": STATE_LABELS.get(state, state),
        "recruit_type_code": "LECTURE",
        "recruit_type_name": "교육회원",
        "apply_period": f"{apply_start}~{apply_end}" if apply_start or apply_end else None,
        "apply_start": apply_start,
        "apply_end": apply_end,
        "selection_announcement": None,
        "dday": calculate_dday(apply_end),
        "recruit_count": row.get("personnel"),
        "occupation_code": str(row.get("facultyId")) if row.get("facultyId") else None,
        "occupation_name": row.get("faculty"),
        "work_condition_code": row.get("type"),
        "work_condition_name": "유료" if row.get("cost") else "무료",
        "career_code": None,
        "career_name": None,
        "fee_amount": row.get("cost"),
        "fee_text": f"{row.get('cost')}원" if row.get("cost") is not None else None,
        "education_start": education_start,
        "education_end": education_end,
        "education_location": row.get("orgName"),
        "pre_edu_yn": None,
        "lecturer": row.get("mainLecturer"),
        "term": row.get("term"),
        "register_count": row.get("registerCnt"),
        "waiting_personnel": row.get("waitingPersonnel"),
        "application_url": source_url,
        "source_url": source_url,
        "crawled_at": datetime.now().isoformat(timespec="seconds"),
        "raw_data": row,
    }


def crawl_lectures(
    limit: int | None = None, state: str = "JOIN"
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = make_session(state)
    first_page = request_page(session, 1, state)
    total_count = int(first_page.get("totalElements") or 0)
    total_pages = int(first_page.get("totalPages") or 1)
    target_count = min(total_count, limit) if limit else total_count

    lectures: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for page in range(1, total_pages + 1):
        payload = first_page if page == 1 else request_page(session, page, state)
        for row in payload.get("content", []):
            lecture_id = row.get("id")
            if lecture_id in seen_ids:
                continue
            seen_ids.add(lecture_id)
            lectures.append(normalize_lecture(row, state))
            if len(lectures) >= target_count:
                return lectures, first_page
        print(f"Fetched {len(lectures):>3}/{target_count} rows")

    return lectures, first_page


def save_outputs(
    lectures: list[dict[str, Any]], output_dir: Path, state: str
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    state_slug = STATE_SLUGS.get(state, state.lower())
    csv_path = output_dir / f"50plus_center_education_{state_slug}.csv"
    json_path = output_dir / f"50plus_center_education_{state_slug}.json"

    flat_fields = [key for key in lectures[0].keys() if key != "raw_data"] if lectures else []
    with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=flat_fields)
        writer.writeheader()
        for lecture in lectures:
            writer.writerow({key: lecture.get(key) for key in flat_fields})

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(lectures, json_file, ensure_ascii=False, indent=2)

    return csv_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl joining 50plus center education lectures."
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to save.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--state",
        default="JOIN",
        choices=sorted(STATE_LABELS),
        help="Lecture recruitment state. JOIN=모집중, PEND=모집예정.",
    )
    args = parser.parse_args()

    try:
        lectures, pagination = crawl_lectures(args.limit, args.state)
        csv_path, json_path = save_outputs(lectures, args.output_dir, args.state)
        print(f"Site totalElements: {pagination.get('totalElements')}")
        print(f"Saved {len(lectures)} unique rows")
        print(f"CSV UTF-8: {csv_path}")
        print(f"JSON UTF-8: {json_path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
