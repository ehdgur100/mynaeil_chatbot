from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict

from langchain_core.messages import AIMessage

from database.connection import supabase
import database.operations as db_ops
from state import AgentState

ACTIVE_STATUSES = ("모집중", "모집예정")
CATEGORIES = ("취업훈련", "AI디지털교육", "50플러스센터교육")
STOP_TERMS = {
    "교육",
    "추천",
    "추천해줘",
    "과정",
    "강의",
    "강좌",
    "근처",
    "관련",
    "있어",
    "알려줘",
    "찾아줘",
    "서울",
}

DIGITAL_KEYWORDS = (
    "디지털",
    "ai",
    "인공지능",
    "스마트폰",
    "컴퓨터",
    "온라인",
    "엑셀",
    "파워포인트",
    "한글",
    "문서",
    "데이터",
    "sns",
    "유튜브",
    "키오스크",
)

BEGINNER_KEYWORDS = ("초보", "기초", "입문", "처음", "기본")
ADVANCED_KEYWORDS = ("실무", "심화", "자격", "프로젝트", "활용", "전문")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", _clean(value).lower())


def _split_terms(*values: Any) -> list[str]:
    text = " ".join(_clean(value) for value in values if value)
    terms = re.split(r"[^0-9A-Za-z가-힣]+", text)
    return [
        term.lower()
        for term in terms
        if len(term) >= 2 and term.lower() not in STOP_TERMS
    ]


def _location_terms(location: str) -> list[str]:
    raw_terms = _split_terms(location)
    terms: list[str] = []
    for term in raw_terms:
        normalized = (
            term.replace("서울시", "")
            .replace("서울", "")
            .replace("특별시", "")
            .replace("거주", "")
        )
        if normalized.endswith("구"):
            normalized = normalized[:-1]
        if normalized and normalized not in ("전국", "경기"):
            terms.append(normalized)
    return terms


def _date_key(value: Any) -> datetime:
    text = _clean(value)
    for fmt in ("%Y-%m-%d", "%Y%m%d%H", "%Y%m%d", "%y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.max


def _date_value(value: Any) -> date | None:
    parsed = _date_key(value)
    if parsed == datetime.max:
        return None
    return parsed.date()


def _is_expired(row: dict[str, Any], today: date | None = None) -> bool:
    apply_end = _date_value(row.get("apply_end"))
    if apply_end is None:
        return False
    return apply_end < (today or date.today())


def _row_text(row: dict[str, Any]) -> str:
    fields = (
        "title",
        "category",
        "provider",
        "business_type_name",
        "occupation_name",
        "education_location",
        "content",
    )
    return " ".join(_clean(row.get(field)) for field in fields).lower()


def _score_row(
    row: dict[str, Any],
    desired_job: str,
    digital_level: str,
    location: str,
    user_input: str,
) -> tuple[int, list[str]]:
    text = _row_text(row)
    compact_text = _compact(text)
    reasons: list[str] = []
    score = 0

    desired_terms = _split_terms(desired_job, user_input)
    matched_job_terms = [
        term for term in desired_terms if term in text or term in compact_text
    ]
    if matched_job_terms:
        score += min(len(matched_job_terms), 3) * 4
        reasons.append(
            f"희망직무 관련 키워드({', '.join(matched_job_terms[:3])})가 교육 내용과 맞습니다"
        )

    digital_terms = [
        term
        for term in _split_terms(digital_level, user_input)
        if term in DIGITAL_KEYWORDS
        or any(keyword in term for keyword in DIGITAL_KEYWORDS)
    ]
    matched_digital_terms = [
        term for term in digital_terms if term in text or term in compact_text
    ]
    if matched_digital_terms:
        score += min(len(matched_digital_terms), 3) * 3
        reasons.append(
            f"디지털역량 키워드({', '.join(matched_digital_terms[:3])})와 연결됩니다"
        )

    if any(
        keyword in _compact(digital_level + " " + user_input)
        for keyword in BEGINNER_KEYWORDS
    ):
        if any(keyword in compact_text for keyword in BEGINNER_KEYWORDS):
            score += 2
            reasons.append("입문/기초 수준에 맞는 과정입니다")

    if any(
        keyword in _compact(digital_level + " " + user_input)
        for keyword in ADVANCED_KEYWORDS
    ):
        if any(keyword in compact_text for keyword in ADVANCED_KEYWORDS):
            score += 2
            reasons.append("실무/활용 수준을 높이는 과정입니다")

    location_matches = [
        term
        for term in _location_terms(location)
        if term and (term in compact_text or f"{term}센터" in compact_text)
    ]
    if location_matches:
        score += 3
        reasons.append(
            f"거주지역({', '.join(location_matches[:2])})과 가까운 기관입니다"
        )

    if not reasons:
        reasons.append("현재 신청 가능한 교육 중 프로필 조건과 비교해 추천했습니다")

    return score, reasons


def _fetch_active_educations(limit: int = 600) -> list[dict[str, Any]]:
    if supabase is None:
        return []
    result = (
        supabase.table("education")
        .select(
            "title,category,recruitment_status,provider,education_location,"
            "apply_start,apply_end,application_url,occupation_name,content,"
            "business_type_name"
        )
        .in_("recruitment_status", list(ACTIVE_STATUSES))
        .limit(limit)
        .execute()
    )
    rows = result.data or []
    return [
        row
        for row in rows
        if row.get("category") in CATEGORIES and not _is_expired(row)
    ]


def _date_for_sort(row: dict[str, Any]) -> datetime:
    if row.get("recruitment_status") == "모집중":
        return _date_key(row.get("apply_end"))
    return _date_key(row.get("apply_start"))


def _format_date_label(row: dict[str, Any]) -> str:
    if row.get("recruitment_status") == "모집중":
        return f"신청마감일: {_clean(row.get('apply_end')) or '확인 필요'}"
    return f"모집시작일: {_clean(row.get('apply_start')) or '확인 필요'}"


def _recommend_educations(
    rows: list[dict[str, Any]],
    desired_job: str,
    digital_level: str,
    location: str,
    user_input: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = [row for row in rows if not _is_expired(row)]
    scored: list[dict[str, Any]] = []
    for row in rows:
        score, reasons = _score_row(
            row, desired_job, digital_level, location, user_input
        )
        if score <= 0:
            continue
        scored.append({**row, "_score": score, "_reasons": reasons})

    if not scored:
        scored = [
            {
                **row,
                "_score": 0,
                "_reasons": ["현재 모집 상태와 신청 가능성을 기준으로 추천했습니다"],
            }
            for row in rows
        ]

    ongoing = [row for row in scored if row.get("recruitment_status") == "모집중"]
    pending = [row for row in scored if row.get("recruitment_status") == "모집예정"]

    ongoing.sort(key=lambda row: (_date_for_sort(row), -row["_score"]))
    pending.sort(key=lambda row: (_date_for_sort(row), -row["_score"]))

    recommendations = ongoing[:limit]
    if len(recommendations) < limit:
        recommendations.extend(pending[: limit - len(recommendations)])
    return recommendations


def _build_response_text(
    recommendations: list[dict[str, Any]],
    desired_job: str,
    digital_level: str,
    location: str,
) -> str:
    if not recommendations:
        return (
            "현재 모집중 또는 모집예정 상태의 맞춤 교육을 찾지 못했습니다.\n"
            "희망직무, 디지털역량, 거주지역을 조금 더 구체적으로 알려주시면 다시 찾아볼게요."
        )

    header = (
        "모집중 교육부터 추천드릴게요.\n"
        f"- 희망직무: {desired_job or '미입력'}\n"
        f"- 디지털역량: {digital_level or '미입력'}\n"
        f"- 거주지역: {location or '미입력'}\n"
    )

    lines = [header]
    for index, row in enumerate(recommendations[:3], start=1):
        reasons = row.get("_reasons", ["조건과 관련 있는 교육입니다"])[0]
        block = (
            "\n"
            f"{index}. {row.get('title')}\n"
            f"- {row.get('category')} / {row.get('recruitment_status')}\n"
            f"- 장소: {row.get('education_location') or row.get('provider') or '확인 필요'}\n"
            f"- {_format_date_label(row)}\n"
            f"- 이유: {reasons}\n"
            f"- 링크: {row.get('application_url')}"
        )
        if len("\n".join(lines) + block) > 900:
            break
        lines.append(block)

    if len(recommendations) > 0:
        guide_note = (
            "\n\n💡 위 과정 중 상세한 신청 방법 및 서류, 사전 준비 팁이 궁금하시다면 "
            "아래의 **'[번호]번 교육 신청 가이드'** 버튼을 눌러보세요!"
        )
        if len("\n".join(lines) + guide_note) <= 1000:
            lines.append(guide_note)

    return "\n".join(lines)


async def edu_recommend(state: AgentState) -> Dict[str, Any]:
    print("[Node] edu_recommend 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""

    profile = db_ops.get_user_profile(user_id) or {}
    desired_job = _clean(profile.get("desired_job") or state.get("desired_job"))
    digital_level = _clean(profile.get("digital_level") or profile.get("skills"))
    location = _clean(profile.get("location") or state.get("location"))

    try:
        rows = _fetch_active_educations()
        recommendations = _recommend_educations(
            rows=rows,
            desired_job=desired_job,
            digital_level=digital_level,
            location=location,
            user_input=user_input,
            limit=3,
        )
        ai_response = _build_response_text(
            recommendations, desired_job, digital_level, location
        )
    except Exception as exc:
        print(f"[Education Recommend Error] {exc}")
        ai_response = (
            "교육 추천 정보를 불러오는 중 문제가 발생했습니다. "
            "잠시 후 다시 시도해 주세요."
        )

    # 실제로 ai_response에 노출된 교육 번호(1~3번)를 파악하여 가이드 퀵리플라이를 동적으로 추가합니다.
    quick_replies = []
    shown_count = 0
    for i in range(1, 4):
        if f"\n{i}. " in ai_response or f"{i}. " in ai_response:
            shown_count = i

    for i in range(1, shown_count + 1):
        quick_replies.append({
            "action": "message",
            "label": f"{i}번 교육 신청 가이드",
            "messageText": f"[CMD]edu_select:{i}"
        })

    quick_replies.extend([
        {"action": "message", "label": "다른 교육 찾기", "messageText": "[CMD]edu_recommend"},
        {"action": "message", "label": "처음으로", "messageText": "[CMD]basic_chat"}
    ])

    kakao_resp = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": ai_response}}],
            "quickReplies": quick_replies,
        },
    }

    return {
        "messages": [ai_response],
        "kakao_response": kakao_resp,
        "intent": "edu_recommend",
    }
