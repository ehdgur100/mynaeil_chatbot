from __future__ import annotations

import re
from typing import Any, Dict

from langchain_core.messages import AIMessage

import database.operations as db_ops
from nodes.education import (
    _clean,
    _display_date,
    _fetch_active_educations,
    _recommend_educations,
)
from state import AgentState


def _line(value: Any, fallback: str = "확인 필요") -> str:
    text = _clean(value)
    return text if text else fallback


def _parse_target_index(user_input: str) -> int:
    match = re.search(r"(\d+)\s*번", _clean(user_input))
    if match:
        number = int(match.group(1))
        if 1 <= number <= 3:
            return number - 1
    return 0


def _extract_previous_recommendation(messages: list[Any], target_index: int) -> dict[str, str] | None:
    pattern = re.compile(
        r"\n(?P<num>[1-3])\.\s*(?P<title>.+?)\n"
        r"-\s*(?P<category>.+?)\s*/\s*(?P<status>.+?)\n"
        r"-\s*장소:\s*(?P<place>.+?)\n"
        r"-\s*(?P<date_label>신청마감일|모집시작일):\s*(?P<date>.+?)\n"
        r"(?:-\s*이유:\s*.+?\n)?"
        r"-\s*링크:\s*(?P<url>\S+)",
        re.DOTALL,
    )
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            continue
        matches = list(pattern.finditer(content))
        if len(matches) > target_index:
            data = matches[target_index].groupdict()
            return {key: value.strip() for key, value in data.items()}
    return None


def _education_to_guide_data(row: dict[str, Any]) -> dict[str, str]:
    is_open = row.get("recruitment_status") == "모집중"
    return {
        "title": _line(row.get("title")),
        "category": _line(row.get("category")),
        "status": _line(row.get("recruitment_status")),
        "place": _line(row.get("education_location") or row.get("provider")),
        "date_label": "신청마감일" if is_open else "모집시작일",
        "date": _display_date(row.get("apply_end" if is_open else "apply_start")),
        "url": _line(row.get("application_url")),
    }


def _build_apply_guide(education: dict[str, str]) -> str:
    title = education["title"]
    category = education["category"]
    status = education["status"]
    place = education["place"]
    date_label = education["date_label"]
    date_value = education["date"]
    url = education["url"]

    return (
        f"{title} 신청 가이드입니다.\n"
        f"- 구분: {category} / {status}\n"
        f"- 장소: {place}\n"
        f"- {date_label}: {date_value}\n"
        f"- 신청링크: {url}\n\n"
        "1. 신청 전 확인\n"
        "- 링크를 열어 교육 일정, 장소, 모집대상, 수강료를 먼저 확인하세요.\n"
        "- 모집중이면 마감일 전에 바로 신청하고, 모집예정이면 시작일을 캘린더에 저장하세요.\n\n"
        "2. 준비할 내용\n"
        "- 이름, 연락처, 거주지역 등 기본 정보를 확인해두세요.\n"
        "- 선발형 과정이면 왜 이 교육이 필요한지 2~3문장으로 준비하세요.\n"
        "- 디지털 과정은 현재 가능한 작업과 배우고 싶은 도구를 짧게 적어두면 좋아요.\n\n"
        "3. 신청 후\n"
        "- 접수 완료 문자나 이메일을 확인하세요.\n"
        "- 교육 전날 장소와 시간을 다시 확인하세요."
    )


async def edu_guide(state: AgentState) -> Dict[str, Any]:
    print("[Node] edu_guide 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    target_index = _parse_target_index(user_input)

    profile = db_ops.get_user_profile(user_id) or {}
    desired_job = _clean(profile.get("desired_job") or state.get("desired_job"))
    digital_level = _clean(profile.get("digital_level") or profile.get("skills"))
    location = _clean(profile.get("location") or state.get("location"))

    try:
        previous = _extract_previous_recommendation(messages, target_index)
        if previous:
            ai_response = _build_apply_guide(previous)
        else:
            rows = _fetch_active_educations()
            recommendations = _recommend_educations(
                rows=rows,
                desired_job=desired_job,
                digital_level=digital_level,
                location=location,
                user_input=user_input,
                limit=3,
            )
            if not recommendations:
                ai_response = (
                    "신청 가이드를 만들 교육을 찾지 못했어요.\n"
                    "먼저 '디지털 교육 추천해줘'처럼 교육 추천을 받은 뒤 "
                    "'1번 교육 신청 가이드'라고 눌러주세요."
                )
            else:
                selected = recommendations[min(target_index, len(recommendations) - 1)]
                ai_response = _build_apply_guide(_education_to_guide_data(selected))
    except Exception as exc:
        print(f"[Education Guide Error] {exc}")
        ai_response = "교육 신청 가이드를 만드는 중 문제가 발생했어요. 잠시 후 다시 시도해주세요."

    kakao_resp = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": ai_response}}],
            "quickReplies": [
                {
                    "action": "message",
                    "label": "교육 추천 다시",
                    "messageText": "교육 추천 다시 해줘",
                }
            ],
        },
    }

    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": kakao_resp,
        "intent": "edu_guide",
    }


from nodes.guide import get_apply_guide

async def apply_guide(state: AgentState) -> Dict[str, Any]:
    print("[Node] apply_guide 실행 (동적 채용 가이드 생성)")
    user_id = state.get("user_id", "unknown")
    
    profile = db_ops.get_user_profile(user_id) or {}
    selected_job_id = profile.get("selected_job_id")
    
    if selected_job_id:
        job = db_ops.get_job_by_id(selected_job_id)
        if job:
            ai_response = await get_apply_guide(job)
        else:
            ai_response = "선택하신 공고 정보를 불러올 수 없습니다. 😥 다시 공고를 선택해 주세요."
    else:
        ai_response = (
            "아직 선택하신 구직 공고가 없습니다. 💼\n\n"
            "먼저 '일자리 검색'이나 '자기소개서 작성' 온보딩 메뉴를 통해 "
            "원하시는 공고를 선택해 주시면 자세한 지원 가이드를 만들어 드릴게요!"
        )
        
    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": ai_response}}]},
        },
        "intent": "apply_guide",
    }
