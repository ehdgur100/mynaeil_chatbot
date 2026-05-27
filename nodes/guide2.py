from __future__ import annotations

import re
from typing import Any, Dict

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

import database.operations as db_ops
from nodes.base import llm_smart, get_content
from nodes.education import (
    _clean,
    _fetch_active_educations,
    _recommend_educations,
)
from state import AgentState


def _line(value: Any, fallback: str = "확인 필요") -> str:
    text = _clean(value)
    return text if text else fallback


def _parse_target_index(user_input: str) -> int:
    """사용자 발화에서 번호(1~3번)나 '첫번째', '두번째' 등의 키워드를 파싱하여 0-indexed 정수를 반환합니다."""
    text = _clean(user_input).lower()
    
    # 1. 숫자 패턴 매칭 (예: "1번", "2번", "3", "1 ")
    num_match = re.search(r"(\d+)\s*(번|순위|번째|차|가지)?", text)
    if num_match:
        try:
            val = int(num_match.group(1))
            if 1 <= val <= 3:
                return val - 1
        except ValueError:
            pass
            
    # 2. 한글 서수 패턴 매칭
    if any(k in text for k in ["첫", "첫번", "일번", "처음", "1"]):
        return 0
    if any(k in text for k in ["둘", "두번", "이번", "2"]):
        return 1
    if any(k in text for k in ["셋", "세번", "삼번", "3"]):
        return 2
        
    return 0


_GUIDE_SYSTEM_PROMPT = """당신은 5060 신중년 구직자의 평생 교육과 취업 성공을 돕는 따뜻하고 전문적인 1:1 취업 밀착 코치입니다.
추천된 교육 과정의 상세 정보와 신청자의 프로필 정보를 종합하여, 맞춤형 '신청 및 준비 가이드'를 작성해 주세요.

작성 가이드라인:
1. 친근하고 힘을 주는 존댓말(해요체)을 사용하세요.
2. 가독성을 높이기 위해 소제목(예: 1., 2.)과 이모티콘을 적극 활용하세요.
3. 카카오톡 메시지 길이 제한(1000자)을 절대 넘지 않도록, '공백 포함 850자 이내'로 핵심만 명확하게 작성하세요.
4. 반드시 포함할 구성 요소:
   - [교육 개요 및 신청처]: 과정명, 교육 구분, 신청 링크(링크는 본문에 그대로 노출할 것)
   - [맞춤형 신청/선발 팁]: 유료/무료 여부(수강료가 유료일 시 배움카드나 지자체 감면 혜택 확인 권장), 선발제인 경우 지원동기 작성 요령
   - [수강 전 사전 준비]: 디지털 역량이 필요하거나(AI디지털교육 등) 면접이 동반되는 직무 교육의 경우 무엇을 사전 학습하거나 마음의 준비를 해야 할지 제시
   - [직무 시너지 응원]: 수료 후 신청자의 희망 직무 및 경력과 어떻게 시너지를 낼 수 있을지 따뜻한 격려
"""

_GUIDE_USER_TEMPLATE = """아래는 지원할 교육 정보와 신청자의 프로필입니다.

[신청할 교육 정보]
- 과정명: {title}
- 카테고리: {category}
- 교육 장소/기관: {place}
- 모집 기간: {apply_start} ~ {apply_end}
- 신청 링크: {url}
- 교육 내용: {content}

[신청자 프로필]
- 희망 직무: {desired_job}
- 디지털역량/보유기술: {skills}
- 핵심 경력: {career}
- 거주 지역: {location}

이 정보를 활용하여, 5060 사용자 맞춤형 프리미엄 '신청 및 준비 가이드'를 작성해 주세요."""


async def _build_education_guide_llm(
    edu: dict[str, Any],
    desired_job: str,
    digital_level: str,
    career: str,
    location: str,
) -> str:
    title = _line(edu.get("title"))
    category = _line(edu.get("category"))
    place = _line(edu.get("education_location") or edu.get("provider"))
    apply_start = _line(edu.get("apply_start"))
    apply_end = _line(edu.get("apply_end"))
    url = _line(edu.get("application_url"))
    content = _line(edu.get("content"))

    user_prompt = _GUIDE_USER_TEMPLATE.format(
        title=title,
        category=category,
        place=place,
        apply_start=apply_start,
        apply_end=apply_end,
        url=url,
        content=content,
        desired_job=desired_job or "미입력",
        skills=digital_level or "기초 수준",
        career=career or "기록 없음",
        location=location or "전국"
    )

    try:
        response = await llm_smart.ainvoke([
            SystemMessage(content=_GUIDE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ])
        ai_response = get_content(response)
        
        # 글자 수 초과 방지를 위한 안전 장치
        if len(ai_response) > 950:
            ai_response = ai_response[:920] + "\n\n(※ 메시지 길이 제한으로 일부 생략되었습니다. 신청 링크를 눌러 상세 내용을 확인해 주세요!)"
        return ai_response
    except Exception as e:
        print(f"[LLM Guide Error] LLM 가이드 작성 실패: {e}")
        # 오류 시 Fallback 로직 (기본 템플릿 반환)
        return (
            f"🎯 **{title}** 신청 준비 가이드\n\n"
            f"- 교육 구분: {category}\n"
            f"- 장소/기관: {place}\n"
            f"- 신청 마감: {apply_end}\n"
            f"- 신청 링크: {url}\n\n"
            "💡 **신청 전 필수 확인 사항**\n"
            "1. 일정 및 위치가 참여 가능한지 꼭 확인하세요.\n"
            "2. 선발형(인터뷰/서류) 과정의 경우, 구직 목적을 명확히 정리해두면 유리합니다.\n"
            "3. 디지털 교육 과정은 기초 기기 활용에 필요한 스마트폰이나 컴퓨터의 사양을 미리 체크해 주세요."
        )


async def edu_guide(state: AgentState) -> Dict[str, Any]:
    print("[Node] edu_guide 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""

    profile = db_ops.get_user_profile(user_id) or {}
    desired_job = _clean(profile.get("desired_job") or state.get("desired_job"))
    digital_level = _clean(profile.get("digital_level") or profile.get("skills"))
    location = _clean(profile.get("location") or state.get("location"))
    career = _clean(profile.get("career"))

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
        
        if not recommendations:
            ai_response = (
                "현재 모집중/모집예정 교육을 찾지 못했어요. 😥\n"
                "프로필 정보를 조금 더 구체적으로 보강하시면 적합한 교육의 신청/준비 가이드를 만들어 드릴게요."
            )
        else:
            # 유저 입력에서 대상 교육 인덱스 파싱
            target_idx = _parse_target_index(user_input)
            if target_idx >= len(recommendations):
                target_idx = 0  # 범위 초과 시 첫 번째 교육
                
            selected_edu = recommendations[target_idx]
            ai_response = await _build_education_guide_llm(
                edu=selected_edu,
                desired_job=desired_job,
                digital_level=digital_level,
                career=career,
                location=location
            )
    except Exception as exc:
        print(f"[Education Guide Error] {exc}")
        ai_response = (
            "교육 신청/준비 가이드를 만드는 중 문제가 발생했어요. 😥\n"
            "잠시 후 다시 시도해 주세요."
        )

    # 퀵리플라이는 자연스럽게 교육 추천으로 돌아가거나, 다른 팁을 볼 수 있도록 연계
    kakao_resp = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": ai_response}}],
            "quickReplies": [
                {
                    "action": "message",
                    "label": "다른 교육 추천받기",
                    "messageText": "나한테 맞는 교육 추천해줘",
                },
                {
                    "action": "message",
                    "label": "구직 가이드북 보기",
                    "messageText": "취업 준비 팁 가이드 알려줘",
                },
            ],
        },
    }

    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": kakao_resp,
        "intent": "edu_guide",
    }
