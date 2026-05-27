import re
from typing import Dict, Any
from state import AgentState
from nodes.base import IntentEnum, llm_fast, get_content
from database.operations import get_user_profile


async def analyze_intent(state: AgentState) -> Dict[str, Any]:
    """
    [의도 분석기 노드]
    사용자의 입력 발화를 분석하여 어떤 기능 노드로 라우팅할지 결정합니다.
    """
    print("[Node] analyze_intent 실행")

    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content.strip() if messages else ""

    # ---------------------------------------------------------
    # Stage 1: 확실한 Rule (명령어 Payload 매칭)
    # ---------------------------------------------------------
    if user_input.startswith("[CMD]"):
        cmd = user_input[5:].strip()
        print(f"[Intent] 명령어 감지: {cmd}")
        
        # 1-1. 특정 공고 선택 처리 (job_select:N)
        if cmd.startswith("job_select:"):
            try:
                idx = int(cmd.split(":")[1]) - 1
                last_jobs = state.get("last_recommended_jobs")
                if last_jobs and 0 <= idx < len(last_jobs):
                    selected = last_jobs[idx]
                    return {"intent": "resume_gen", "selected_job": selected}
            except Exception as e:
                print(f"[Intent Warning] 공고 선택 명령어 파싱 오류: {e}")
            return {"intent": "job_search"}  # 오류 시 다시 검색으로 롤백

        # 1-2. 특정 교육 선택 처리 (edu_select:N)
        if cmd.startswith("edu_select:"):
            # edu_guide 노드 내부에서 텍스트의 숫자(N)를 스스로 파싱하므로 그대로 통과
            return {"intent": "edu_guide"}

        # 1-3. 일반 명시적 명령어 처리
        if cmd in IntentEnum.__members__:
            return {"intent": cmd}
            
        return {"intent": "basic_chat"}

    # ---------------------------------------------------------
    # Stage 1.5: 단순 인사말 초고속 패스 (LLM 지연 밎 카카오 타임아웃 방지)
    # ---------------------------------------------------------
    GREETING_KEYWORDS = ["안녕", "하이", "반가워", "반갑", "hi", "hello", "누구", "소개", "이름"]
    clean_input = user_input.replace(" ", "").lower()
    if any(k in clean_input for k in GREETING_KEYWORDS) and len(user_input) <= 15:
        print("[Intent] 인사말 감지 -> basic_chat 빠른 라우팅")
        return {"intent": "basic_chat"}

    # ---------------------------------------------------------
    # Stage 2: 강제 락인 (자소서 온보딩 및 수정 중)
    # ---------------------------------------------------------
    # 명령어가 아닌 일반 텍스트 입력 시, 현재 상태가 자소서 작성/수정 루프에 빠져있다면 무조건 유지합니다.
    try:
        profile = get_user_profile(user_id)
        if profile is not None:
            step = profile.get("step", 0)
            resume_status = profile.get("resume_status", "none")

            is_onboarding = 0 <= step < 9
            is_resume_active = resume_status in ["generated", "reviewed", "editing"]

            # 'done' 상태일 때 텍스트를 입력하면 'resume_gen' 노드에서 "어떻게 수정해드릴까요?" 흐름을 타거나 기본 안내로 빠짐.
            if is_onboarding or is_resume_active or resume_status == "done":
                # 단, 사용자가 인사말 등 너무 명백한 텍스트를 칠 수도 있으므로 최소한의 탈출구 마련 (처음부터)
                if user_input.replace(" ", "") in ["처음부터", "초기화", "다시시작"]:
                    return {"intent": "resume_gen"}
                    
                print(f"[Intent] 락인(Lock-in) 감지 (step: {step}, status: {resume_status}) → resume_gen 강제 라우팅")
                return {"intent": "resume_gen"}
    except Exception as e:
        print(f"[Intent Warning] 온보딩 사전 확인 실패: {e}")

    # ---------------------------------------------------------
    # Stage 3: 순수 AI NLU (자연어 처리 전담)
    # ---------------------------------------------------------
    # 어설픈 하드코딩 키워드(단어 포함 여부)를 모두 삭제하고, 자유 발화는 무조건 AI에게 맡깁니다.
    print(f"[Intent] 자유 발화 AI 분류 시작: {user_input}")
    system_prompt = (
        "당신은 중장년층 구직자 지원 시스템의 라우터입니다.\n"
        "아래 사용자 발화를 분류하여 다음 카테고 단어 중 '오직 한 단어'로만 답변하십시오:\n"
        "(resume_gen, resume_verify, job_search, edu_recommend, edu_guide, basic_chat)\n\n"
        "규칙:\n"
        "1. 사용자의 의도가 불명확하거나 단순히 인사말(안녕 등)이거나 위 기능에 정확히 부합하지 않으면 무조건 'basic_chat'을 반환하세요.\n"
        "2. 일자리를 찾아달라고 하면 'job_search'.\n"
        "3. 교육/강의를 추천해달라고 하면 'edu_recommend'.\n"
        "4. 특정 교육의 신청 방법/가이드를 물어보면 'edu_guide'.\n"
        "5. 자기소개서 작성을 원하면 'resume_gen'.\n"
        "6. 작성된 자기소개서를 평가/첨삭해달라고 하면 'resume_verify'.\n"
        "7. 다른 서술어나 기호, 백틱(```) 등은 절대 포함하지 마십시오."
    )

    try:
        response = await llm_fast.ainvoke(
            f"{system_prompt}\n\n사용자 발화: {user_input}"
        )
        res_text = get_content(response)

        # 알파벳만 남기고 정규식으로 안전하게 청소
        cleaned_intent = re.sub(r"[^a-zA-Z_]", "", res_text)

        if cleaned_intent in IntentEnum.__members__:
            analyzed_intent = cleaned_intent
        else:
            analyzed_intent = "basic_chat"
    except Exception as e:
        print(f"[Intent LLM Error] 의도 분석 실패: {e}")
        analyzed_intent = "basic_chat"

    print(f"[Intent] AI 최종 판별: {analyzed_intent}")
    print(f"[Intent] AI 최종 판별: {analyzed_intent}")
    return {"intent": analyzed_intent}
