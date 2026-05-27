import re
from typing import Any, Dict

from database.operations import get_user_profile
from nodes.base import IntentEnum, get_content, llm_fast
from state import AgentState


RESET_KEYWORDS = ("처음부터", "초기화", "다시 시작")
EDU_WORDS = ("교육", "강의", "강좌", "과정", "훈련", "직업훈련", "수강", "디지털역량")
EDU_GUIDE_WORDS = ("가이드", "준비", "신청", "방법", "어떻게", "서류", "수료", "이후")
JOB_WORDS = ("일자리", "알바", "취업", "구인", "공고", "일할", "채용", "직무 추천")
RESUME_WORDS = ("이력서", "자기소개서", "자소서", "경력", "자소서 보여줘", "저장된 자소서")
VERIFY_WORDS = ("검증", "평가", "첨삭", "피드백", "자소서 수정")
GREETING_WORDS = ("안녕", "하이", "반가", "뭐해", "누구", "이름")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _is_education_guide(text: str) -> bool:
    numbered_guide = re.search(r"\d+\s*번\s*(교육|과정)?\s*(신청|가이드|준비)", text)
    return bool(numbered_guide) or (
        _contains_any(text, EDU_WORDS) and _contains_any(text, EDU_GUIDE_WORDS)
    )


def _is_education_recommend(text: str) -> bool:
    return _contains_any(text, EDU_WORDS)


def _is_job_search(text: str) -> bool:
    return _contains_any(text, JOB_WORDS)


async def analyze_intent(state: AgentState) -> Dict[str, Any]:
    print("[Node] analyze_intent 실행")

    current_intent = state.get("intent")
    if current_intent:
        return {"intent": current_intent}

    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    text = user_input.strip().lower()

    if _contains_any(text, GREETING_WORDS):
        return {"intent": "basic_chat"}

    if _is_education_guide(text):
        return {"intent": "edu_guide"}

    if _is_education_recommend(text):
        return {"intent": "edu_recommend"}

    if _is_job_search(text):
        return {"intent": "job_search"}

    if _contains_any(text, VERIFY_WORDS):
        return {"intent": "resume_verify"}

    if _contains_any(text, RESUME_WORDS):
        return {"intent": "resume_gen"}

    try:
        profile = get_user_profile(user_id)
        if profile is not None:
            resume_status = profile.get("resume_status", "none") or "none"
            if resume_status.startswith("edu_") and not _contains_any(text, RESET_KEYWORDS):
                return {"intent": "edu_recommend"}

            step = profile.get("step", 0)
            is_onboarding = 0 <= step < 9
            is_resume_active = resume_status in ("generated", "reviewed", "editing", "done")
            if (is_onboarding or is_resume_active) and not _contains_any(text, RESET_KEYWORDS):
                return {"intent": "resume_gen"}
    except Exception as exc:
        print(f"[Intent Warning] profile check failed: {exc}")

    system_prompt = (
        "당신은 중장년층 구직자 지원 시스템의 의도 분석가입니다.\n"
        "아래 사용자 발화를 다음 카테고리 중 하나로만 분류하세요:\n"
        "(resume_gen, resume_verify, job_search, edu_recommend, edu_guide, apply_guide, basic_chat)\n"
        "다른 설명 없이 카테고리 단어 하나만 답하세요."
    )

    try:
        response = await llm_fast.ainvoke(f"{system_prompt}\n\n사용자 발화: {user_input}")
        cleaned_intent = re.sub(r"[^a-zA-Z_]", "", get_content(response))
        if cleaned_intent in IntentEnum.__members__:
            return {"intent": cleaned_intent}
    except Exception as exc:
        print(f"[Intent LLM Error] {exc}")

    return {"intent": "basic_chat"}
