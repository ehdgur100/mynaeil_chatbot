import re
from typing import Dict, Any
from state import AgentState
from nodes.base import IntentEnum, llm_fast, get_content
from database.operations import get_user_profile

async def analyze_intent(state: AgentState) -> Dict[str, Any]:
    """
    사용자의 발화 의도를 분석하는 랭그래프 라우터 노드.
    - 유저가 현재 자소서 작성 온보딩 질문에 답하는 중이라면 다른 의도로 혼선되지 않게 강제로 resume_gen으로 넘깁니다.
    """
    print("[Node] analyze_intent 실행")
    
    # 1. 퀵Extra 등으로 명시적 주입된 의도가 있다면 그대로 사용
    current_intent = state.get("intent")
    if current_intent:
        return {"intent": current_intent}
        
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    input_clean = user_message = user_input.strip().lower()

    # 2. 온보딩 진행 체크 (Smart Bypass)
    # RAG/DB 엔지니어가 구현한 operations 모듈을 통해 온보딩이 안 끝났는지 조회합니다.
    # 단, 유저가 명시적으로 자소서 '검증/피드백'을 원하는 경우에는 온보딩 강제 루프를 적용하지 않습니다.
    try:
        profile = get_user_profile(user_id)
        if profile is not None:
            step = profile.get("step", 0)
            # 온보딩 중간 단계 (0~6) 인 경우 무조건 자소서 온보딩으로 다이렉트 바인딩
            if 0 <= step < 7 and not any(k in input_clean for k in ["검증", "평가", "첨삭", "피드백", "판별"]):
                # 단, 유저가 완전히 "처음부터"를 입력했을 때는 온보딩을 리셋해야 하므로 resume_gen으로 분기시킴
                print(f"[Intent] 온보딩 진행 유저 확인 (현재 step: {step}) → 자소서 루프 강제 라우팅")
                return {"intent": "resume_gen"}
    except Exception as e:
        print(f"[Intent Warning] 온보딩 사전 확인 실패: {e}")

    # 3. 초고속 하드코딩 키워드 라우팅 (비용 절감 및 레이턴시 최소화)
    if any(k in input_clean for k in ["안녕", "누구", "반가워", "하이", "이름", "뭐해"]):
        return {"intent": "basic_chat"}

    if any(k in input_clean for k in ["검증", "평가", "첨삭", "피드백", "판별"]):
        return {"intent": "resume_verify"}
    if any(k in input_clean for k in ["이력서", "자기소개서", "자소서", "경력", "면접", "처음부터", "자소서 보여줘", "저장된 자소서"]):
        return {"intent": "resume_gen"}
    if any(k in input_clean for k in ["일자리", "알바", "취업", "구인", "공고", "일할", "채용", "추천"]):
        return {"intent": "job_search"}
    if any(k in input_clean for k in ["가이드", "방법", "준비", "팁", "어떻게"]):
        return {"intent": "apply_guide"}

    # 4. LLM 기반 의도 분류 요청 (llm_fast 모델 활용)
    system_prompt = (
        "당신은 중장년층 구직자 지원 시스템의 의도 분석가입니다.\n"
        "아래 사용자 발화를 분류하여 다음 카테고리 단어 중 '오직 한 단어'로만 답변하십시오:\n"
        "(resume_gen, resume_verify, job_search, apply_guide, basic_chat)\n"
        "다른 서술어나 기호, 백틱(```) 등은 포함하지 마십시오."
    )
    
    try:
        response = await llm_fast.ainvoke(f"{system_prompt}\n\n사용자 발화: {user_input}")
        res_text = get_content(response)
        
        # 불필요한 특수 기호/줄바꿈/공백 정규식으로 안전하게 청소
        cleaned_intent = re.sub(r'[^a-zA-Z_]', '', res_text)
        
        if cleaned_intent in IntentEnum.__members__:
            analyzed_intent = cleaned_intent
        else:
            analyzed_intent = "basic_chat"
    except Exception as e:
        print(f"[Intent LLM Error] 의도 분석 실패: {e}")
        analyzed_intent = "basic_chat"
        
    return {"intent": analyzed_intent}
