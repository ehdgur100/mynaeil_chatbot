import re
from typing import Any, Dict

from database.operations import get_user_profile
from nodes.base import IntentEnum, get_content, llm_fast
from nodes.navigation import is_home_request, is_previous_request
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


def is_explicit_menu_command(text: str) -> bool:
    clean = re.sub(r"[^\w\s]", "", text).strip()
    normalized = " ".join(clean.split())
    menu_commands = {
        "일자리 검색", "일자리검색",
        "교육 추천", "교육추천",
        "자기소개서 작성", "자기소개서작성", "자소서 작성", "자소서작성",
        "처음으로", "처음", "메인", "홈", "초기화", "처음부터", "다시 시작"
    }
    return normalized in menu_commands


async def analyze_intent(state: AgentState) -> Dict[str, Any]:
    print("[Node] analyze_intent 실행")

    current_intent = state.get("intent")
    if current_intent:
        return {"intent": current_intent}

    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    text = user_input.strip().lower()

    if is_home_request(user_input):
        return {"intent": "basic_chat"}

    if _contains_any(text, GREETING_WORDS):
        return {"intent": "basic_chat"}

    if is_previous_request(user_input):
        recent_text = "\n".join(
            str(getattr(message, "content", ""))
            for message in messages[:-1][-4:]
        )
        if any(
            keyword in recent_text
            for keyword in ("교육 추천", "교육 신청", "신청마감일", "모집시작일")
        ):
            return {"intent": "edu_recommend"}

        try:
            profile = get_user_profile(user_id)
            if profile:
                resume_status = profile.get("resume_status", "none") or "none"
                if resume_status.startswith("edu_"):
                    return {"intent": "edu_recommend"}

                step = profile.get("step", 0) or 0
                if 0 < step < 9 or resume_status in (
                    "jobs_recommended",
                    "generated",
                    "reviewed",
                    "editing",
                    "done",
                ):
                    return {"intent": "resume_gen"}
        except Exception as exc:
            print(f"[Intent Previous Warning] profile check failed: {exc}")
        return {"intent": "basic_chat"}

    # 프로필을 한 번 조회해 조기 우회와 후기 Smart Bypass 양쪽에서 재사용
    profile = None
    step = 0
    resume_status = "none"
    try:
        profile = get_user_profile(user_id)
        if profile is not None:
            step = profile.get("step", 0) or 0
            resume_status = profile.get("resume_status", "none") or "none"
    except Exception as exc:
        print(f"[Intent Warning] profile check failed: {exc}")

    if profile is not None:
        if resume_status.startswith("edu_") and not _contains_any(text, RESET_KEYWORDS):
            return {"intent": "edu_recommend"}

        # 온보딩 진행 중(step 1~8) 또는 공고 추천 직후 상태에서는 키워드 체크보다
        # 먼저 resume_gen으로 라우팅 — 답변 텍스트에 "취업" 등 키워드가 섞여도 오분류 방지
        # 단, "일자리 검색" 등 명시적인 메뉴 커맨드가 유입된 경우는 제외
        if (0 < step < 9 or resume_status == "jobs_recommended") and not is_explicit_menu_command(text):
            return {"intent": "resume_gen"}

    # 키워드 기반 라우팅 (활성 온보딩 상태가 아닐 때만 도달)
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

    # 후기 Smart Bypass: editing / done 등 나머지 활성 상태 처리
    if profile is not None:
        is_onboarding = 0 <= step < 9
        is_resume_active = resume_status in ("generated", "reviewed", "editing", "done")
        if is_onboarding or is_resume_active:
            return {"intent": "resume_gen"}

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
