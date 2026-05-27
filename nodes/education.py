from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict

from langchain_core.messages import AIMessage

import database.operations as db_ops
from database.connection import supabase
from nodes.navigation import is_previous_request, main_menu_response
from state import AgentState


ACTIVE_STATUSES = ("모집중", "모집예정")
CATEGORIES = ("취업훈련", "AI디지털교육", "50플러스센터교육")

STOP_TERMS = {
    "교육",
    "교육추천",
    "추천",
    "추천해줘",
    "과정",
    "강의",
    "강좌",
    "수업",
    "훈련",
    "근처",
    "관련",
    "있는",
    "있어",
    "알려줘",
    "찾아줘",
    "보여줘",
    "서울",
    "서울시",
    "모집중",
    "모집예정",
    "모집예고",
}

DIGITAL_KEYWORDS = (
    "디지털",
    "ai",
    "인공지능",
    "챗gpt",
    "chatgpt",
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

CATEGORY_HINTS = {
    "취업훈련": ("취업훈련", "직업훈련", "일자리훈련", "구직훈련"),
    "AI디지털교육": ("ai", "디지털", "인공지능", "스마트폰", "컴퓨터", "챗gpt", "chatgpt"),
    "50플러스센터교육": ("센터교육", "50플러스센터", "센터 강의", "센터 과정"),
}


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


def _location_terms(*values: str) -> list[str]:
    raw_terms = _split_terms(*values)
    terms: list[str] = []
    for term in raw_terms:
        normalized = (
            term.replace("서울특별시", "")
            .replace("서울시", "")
            .replace("서울", "")
            .replace("특별시", "")
            .replace("거주", "")
        )
        if normalized.endswith("구"):
            normalized = normalized[:-1]
        if normalized and normalized not in ("전국", "경기", "근처"):
            terms.append(normalized)
    return list(dict.fromkeys(terms))


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


def _display_date(value: Any) -> str:
    parsed = _date_value(value)
    if parsed is not None:
        return parsed.isoformat()
    return _clean(value) or "확인 필요"


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


def _requested_status(user_input: str) -> str | None:
    compact = _compact(user_input)
    if "모집예정" in compact or "모집예고" in compact or "예정" in compact:
        return "모집예정"
    if "모집중" in compact or "신청가능" in compact:
        return "모집중"
    return None


def _requested_categories(user_input: str) -> list[str]:
    compact = _compact(user_input)
    categories: list[str] = []
    for category, hints in CATEGORY_HINTS.items():
        if any(_compact(hint) in compact for hint in hints):
            categories.append(category)
    return categories


def _query_terms(desired_job: str, user_input: str) -> list[str]:
    terms = _split_terms(desired_job, user_input)
    location_like = set(_location_terms(user_input))
    category_words = {
        "ai",
        "디지털",
        "센터교육",
        "취업훈련",
        "직업훈련",
        "모집",
        "예정",
    }
    return [
        term
        for term in terms
        if term not in location_like and term not in category_words
    ]


def _has_specific_request(
    desired_job: str,
    digital_level: str,
    location: str,
    user_input: str,
) -> bool:
    return bool(
        _query_terms(desired_job, user_input)
        or _requested_categories(user_input)
        or _location_terms(location, user_input)
        or any(keyword in _compact(digital_level + " " + user_input) for keyword in DIGITAL_KEYWORDS)
    )


def _score_row(
    row: dict[str, Any],
    desired_job: str,
    digital_level: str,
    location: str,
    user_input: str,
) -> tuple[int, list[str]]:
    title = _clean(row.get("title")).lower()
    category = _clean(row.get("category"))
    text = _row_text(row)
    compact_text = _compact(text)
    compact_query = _compact(" ".join([desired_job, digital_level, location, user_input]))
    reasons: list[str] = []
    score = 0

    requested_categories = _requested_categories(user_input)
    if requested_categories:
        if category in requested_categories:
            score += 10
            reasons.append(f"요청하신 {category} 유형의 교육입니다")
        else:
            return 0, []

    terms = _query_terms(desired_job, user_input)
    title_matches = [term for term in terms if term in title or term in _compact(title)]
    content_matches = [
        term
        for term in terms
        if term not in title_matches and (term in text or term in compact_text)
    ]
    if title_matches:
        score += min(len(title_matches), 3) * 7
        reasons.append(f"질문 키워드({', '.join(title_matches[:3])})가 교육명과 직접 맞습니다")
    if content_matches:
        score += min(len(content_matches), 3) * 3
        reasons.append(f"관련 키워드({', '.join(content_matches[:3])})가 교육 내용과 연결됩니다")

    digital_requested = any(keyword in compact_query for keyword in DIGITAL_KEYWORDS)
    if digital_requested:
        if category == "AI디지털교육" or any(keyword in compact_text for keyword in DIGITAL_KEYWORDS):
            score += 8
            reasons.append("디지털/AI 역량과 관련된 교육입니다")
        elif not terms and not requested_categories:
            return 0, []

    if any(keyword in compact_query for keyword in BEGINNER_KEYWORDS):
        if any(keyword in compact_text for keyword in BEGINNER_KEYWORDS):
            score += 3
            reasons.append("입문/기초 수준에 맞는 과정입니다")
    if any(keyword in compact_query for keyword in ADVANCED_KEYWORDS):
        if any(keyword in compact_text for keyword in ADVANCED_KEYWORDS):
            score += 3
            reasons.append("실무/활용 수준을 높이는 과정입니다")

    location_matches = [
        term
        for term in _location_terms(location, user_input)
        if term and (term in compact_text or f"{term}센터" in compact_text)
    ]
    if location_matches:
        score += 5
        reasons.append(f"요청 지역({', '.join(location_matches[:2])})과 가까운 교육입니다")

    if score > 0 and not reasons:
        reasons.append("질문 조건과 비교해 관련성이 높은 교육입니다")

    return score, reasons


def _fetch_active_educations(limit: int = 1000) -> list[dict[str, Any]]:
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


def _status_rank(row: dict[str, Any]) -> int:
    return 0 if row.get("recruitment_status") == "모집중" else 1


def _format_date_label(row: dict[str, Any]) -> str:
    if row.get("recruitment_status") == "모집중":
        return f"신청마감일: {_display_date(row.get('apply_end'))}"
    return f"모집시작일: {_display_date(row.get('apply_start'))}"


def _recommend_educations(
    rows: list[dict[str, Any]],
    desired_job: str,
    digital_level: str,
    location: str,
    user_input: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    requested_status = _requested_status(user_input)
    rows = [row for row in rows if not _is_expired(row)]
    if requested_status:
        rows = [row for row in rows if row.get("recruitment_status") == requested_status]

    scored: list[dict[str, Any]] = []
    for row in rows:
        score, reasons = _score_row(
            row, desired_job, digital_level, location, user_input
        )
        if score > 0:
            scored.append({**row, "_score": score, "_reasons": reasons})

    if not scored and not _has_specific_request(
        desired_job, digital_level, location, user_input
    ):
        scored = [
            {
                **row,
                "_score": 0,
                "_reasons": ["현재 신청 가능한 교육 중 마감일이 가까운 순서로 추천했습니다"],
            }
            for row in rows
        ]

    scored.sort(key=lambda row: (_status_rank(row), -row["_score"], _date_for_sort(row)))
    return scored[:limit]


def _build_response_text(
    recommendations: list[dict[str, Any]],
    desired_job: str,
    digital_level: str,
    location: str,
) -> str:
    if not recommendations:
        return (
            "질문과 직접 맞는 모집중/모집예정 교육을 찾지 못했습니다.\n"
            "예를 들어 '강서구 디지털', '요양보호사', 'AI 기초', '취업훈련'처럼 "
            "직무나 지역을 조금 더 구체적으로 알려주시면 다시 찾아볼게요."
        )

    header = (
        "질문과 관련성이 높은 교육부터 추천드릴게요.\n"
        f"- 희망직무: {desired_job or '미입력'}\n"
        f"- 디지털역량: {digital_level or '미입력'}\n"
        f"- 거주지역: {location or '미입력'}\n"
    )

    lines = [header]
    for index, row in enumerate(recommendations[:3], start=1):
        reasons = row.get("_reasons", ["질문 조건과 관련 있는 교육입니다"])[0]
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

    guide_note = "\n\n📋 상세한 신청 방법과 준비 팁이 필요하면 아래의 '[번호]번 교육 신청 가이드' 버튼을 눌러주세요."
    if len("\n".join(lines) + guide_note) <= 1000:
        lines.append(guide_note)

    return "\n".join(lines)


async def edu_recommend(state: AgentState) -> Dict[str, Any]:
    print("[Node] edu_recommend 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""

    profile = db_ops.get_user_profile(user_id)
    if profile is None:
        try:
            db_ops.create_user_profile(user_id)
            profile = db_ops.get_user_profile(user_id) or {}
        except Exception as e:
            print(f"[Education Profile Check Error] {e}")
            profile = {}

    resume_status = profile.get("resume_status", "none") or "none"

    if is_previous_request(user_input):
        if resume_status == "edu_step2":
            try:
                supabase.table("users").update({"resume_status": "edu_step1"}).eq("user_id", user_id).execute()
            except Exception as e:
                print(f"[Edu Previous Step Error] {e}")
            text = (
                "이전 단계로 돌아갈게요.\n\n"
                "희망하시는 직무(분야)가 무엇인가요?\n"
                "아래 버튼을 선택하거나 직접 입력해 주세요."
            )
            quick_replies = ["생산·제조", "돌봄·요양", "청소·환경미화", "경비·시설관리", "배달·운전", "사무·행정", "상관없음"]
            return {
                "messages": [AIMessage(content=text)],
                "kakao_response": {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": text}}],
                        "quickReplies": [
                            {"action": "message", "label": label, "messageText": label}
                            for label in quick_replies
                        ],
                    },
                },
                "intent": "edu_recommend",
            }

        if resume_status == "edu_step3":
            try:
                supabase.table("users").update({"resume_status": "edu_step2"}).eq("user_id", user_id).execute()
            except Exception as e:
                print(f"[Edu Previous Step Error] {e}")
            text = (
                "이전 단계로 돌아갈게요.\n\n"
                "디지털 역량 수준은 어느 정도이신가요?\n"
                "아래 버튼에서 선택하거나 직접 입력해 주세요! 💻"
            )
            quick_replies = ["왕초보/기초", "일반/스마트폰 활용", "컴퓨터/엑셀 활용", "AI/챗GPT 활용", "상관없음"]
            return {
                "messages": [AIMessage(content=text)],
                "kakao_response": {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": text}}],
                        "quickReplies": [
                            {"action": "message", "label": label, "messageText": label}
                            for label in quick_replies
                        ],
                    },
                },
                "intent": "edu_recommend",
            }

        if profile.get("skills"):
            try:
                supabase.table("users").update({"resume_status": "edu_step3"}).eq("user_id", user_id).execute()
            except Exception as e:
                print(f"[Edu Previous Step Error] {e}")
            text = (
                "이전 단계로 돌아갈게요.\n\n"
                "주로 어느 거주지역에서 교육을 받고 싶으신가요? 📍\n"
                "아래 버튼을 선택하거나 직접 입력해 주세요."
            )
            quick_replies = ["서울 전체", "서울 강서구", "서울 마포구", "서울 서초구", "상관없음"]
            return {
                "messages": [AIMessage(content=text)],
                "kakao_response": {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": text}}],
                        "quickReplies": [
                            {"action": "message", "label": label, "messageText": label}
                            for label in quick_replies
                        ],
                    },
                },
                "intent": "edu_recommend",
            }

        if profile.get("desired_job"):
            try:
                supabase.table("users").update({"resume_status": "edu_step2"}).eq("user_id", user_id).execute()
            except Exception as e:
                print(f"[Edu Previous Step Error] {e}")
            text = (
                "이전 단계로 돌아갈게요.\n\n"
                "디지털 역량 수준은 어느 정도이신가요?\n"
                "아래 버튼에서 선택하거나 직접 입력해 주세요! 💻"
            )
            quick_replies = ["왕초보/기초", "일반/스마트폰 활용", "컴퓨터/엑셀 활용", "AI/챗GPT 활용", "상관없음"]
            return {
                "messages": [AIMessage(content=text)],
                "kakao_response": {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": text}}],
                        "quickReplies": [
                            {"action": "message", "label": label, "messageText": label}
                            for label in quick_replies
                        ],
                    },
                },
                "intent": "edu_recommend",
            }

        return {
            "messages": [AIMessage(content="이전 단계가 없어 처음 화면으로 돌아갈게요.")],
            "kakao_response": main_menu_response(
                "이전 단계가 없어 처음 화면으로 돌아갈게요.\n\n"
                "아래 메뉴 중 필요한 기능을 선택해주세요."
            ),
            "intent": "basic_chat",
        }

    # 만약 사용자가 교육 추천 메뉴 자체를 처음 클릭하거나, 상태가 비어있다면 온보딩 1단계 시작
    if (
        user_input in ("🎓 교육 추천", "교육 추천", "교육추천")
        or resume_status not in ("edu_step1", "edu_step2", "edu_step3")
    ):
        try:
            supabase.table("users").update({"resume_status": "edu_step1"}).eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[Edu Onboarding Start Error] {e}")

        text = (
            "🎓 *나의내일 맞춤 교육 추천*을 시작합니다!\n\n"
            "더 적합한 교육 과정을 추천해 드리기 위해 3가지 정보를 여쭤볼게요. 😊\n\n"
            "첫 번째로, *희망하시는 직무(분야)*가 무엇인가요?\n"
            "아래 버튼을 선택하거나 직접 입력해 주세요."
        )
        quick_replies = ["생산·제조", "돌봄·요양", "청소·환경미화", "경비·시설관리", "배달·운전", "사무·행정", "상관없음"]

        return {
            "messages": [AIMessage(content=text)],
            "kakao_response": {
                "version": "2.0",
                "template": {
                    "outputs": [{"simpleText": {"text": text}}],
                    "quickReplies": [
                        {"action": "message", "label": label, "messageText": label}
                        for label in quick_replies
                    ],
                },
            },
            "intent": "edu_recommend",
        }

    # 온보딩 진행 단계 처리
    elif resume_status == "edu_step1":
        desired_job = user_input.strip()
        try:
            supabase.table("users").update({
                "desired_job": desired_job,
                "resume_status": "edu_step2"
            }).eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[Edu Step 1 Save Error] {e}")

        text = (
            f"💼 희망직무: *{desired_job}*\n\n"
            "두 번째로, 컴퓨터나 스마트폰 등을 다루는 *디지털 역량 수준*은 어느 정도이신가요?\n"
            "아래 버튼에서 선택하거나 직접 입력해 주세요! 💻"
        )
        quick_replies = ["왕초보/기초", "일반/스마트폰 활용", "컴퓨터/엑셀 활용", "AI/챗GPT 활용", "상관없음"]

        return {
            "messages": [AIMessage(content=text)],
            "kakao_response": {
                "version": "2.0",
                "template": {
                    "outputs": [{"simpleText": {"text": text}}],
                    "quickReplies": [
                        {"action": "message", "label": label, "messageText": label}
                        for label in quick_replies
                    ],
                },
            },
            "intent": "edu_recommend",
        }

    elif resume_status == "edu_step2":
        digital_level = user_input.strip()
        try:
            supabase.table("users").update({
                "skills": digital_level,
                "resume_status": "edu_step3"
            }).eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[Edu Step 2 Save Error] {e}")

        text = (
            f"💻 디지털역량: *{digital_level}*\n\n"
            "마지막으로, 주로 어느 *거주지역*에서 교육을 받고 싶으신가요? 📍\n"
            "(예: 서울 강서구, 경기 수원시, 전국 등)\n"
            "아래 버튼을 선택하거나 직접 입력해 주세요."
        )
        quick_replies = ["서울 전체", "서울 강서구", "서울 마포구", "서울 서초구", "상관없음"]

        return {
            "messages": [AIMessage(content=text)],
            "kakao_response": {
                "version": "2.0",
                "template": {
                    "outputs": [{"simpleText": {"text": text}}],
                    "quickReplies": [
                        {"action": "message", "label": label, "messageText": label}
                        for label in quick_replies
                    ],
                },
            },
            "intent": "edu_recommend",
        }

    elif resume_status == "edu_step3":
        location = user_input.strip()
        try:
            supabase.table("users").update({
                "location": location,
                "resume_status": "none"
            }).eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[Edu Step 3 Save Error] {e}")

        # 수집 완료 후, 즉시 맞춤 추천을 실행하기 위해 DB 프로필 다시 조회
        profile = db_ops.get_user_profile(user_id) or {}
        desired_job = _clean(profile.get("desired_job"))
        digital_level = _clean(profile.get("skills"))
        location = _clean(profile.get("location"))

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

        quick_replies = []
        shown_count = 0
        for i in range(1, 4):
            if f"\n{i}. " in ai_response or f"{i}. " in ai_response:
                shown_count = i

        for i in range(1, shown_count + 1):
            quick_replies.append(f"📋 {i}번 교육 신청 가이드")

        quick_replies.extend(["🔎 모집중 교육 더 보기", "🗓️ 모집예정 교육 보기", "🎓 다른 교육 찾기"])

        kakao_resp = {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": ai_response}}],
                "quickReplies": [
                    {"action": "message", "label": label, "messageText": label}
                    for label in quick_replies
                ],
            },
        }

        return {
            "messages": [AIMessage(content=ai_response)],
            "kakao_response": kakao_resp,
            "intent": "edu_recommend",
        }

    # 기본 폴백 추천 (혹시 모를 상태 꼬임 방지)
    else:
        desired_job = _clean(profile.get("desired_job"))
        digital_level = _clean(profile.get("skills"))
        location = _clean(profile.get("location"))

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
            print(f"[Education Recommend Fallback Error] {exc}")
            ai_response = "교육 추천 과정 중 오류가 발생하여 기본 목록을 불러옵니다. 잠시 후 다시 시도해 주세요."

        quick_replies = []
        shown_count = 0
        for i in range(1, 4):
            if f"\n{i}. " in ai_response or f"{i}. " in ai_response:
                shown_count = i

        for i in range(1, shown_count + 1):
            quick_replies.append(f"📋 {i}번 교육 신청 가이드")

        quick_replies.extend(["🔎 모집중 교육 더 보기", "🗓️ 모집예정 교육 보기", "🎓 다른 교육 찾기"])

        kakao_resp = {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": ai_response}}],
                "quickReplies": [
                    {"action": "message", "label": label, "messageText": label}
                    for label in quick_replies
                ],
            },
        }

        return {
            "messages": [AIMessage(content=ai_response)],
            "kakao_response": kakao_resp,
            "intent": "edu_recommend",
        }
