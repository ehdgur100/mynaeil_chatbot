import re
from typing import Dict, Any
from state import AgentState
from nodes.base import IntentEnum, llm_fast, get_content
from database.operations import get_user_profile

async def analyze_intent(state: AgentState) -> Dict[str, Any]:
    """
    [의도 분석기 노드]
    사용자의 입력 발화를 분석하여 어떤 카테고리(자소서 작성, 자소서 검증, 일자리 찾기 등)로 이동할지 라우팅 의도를 결정합니다.
    """
    print("[Node] analyze_intent 실행")
    
    # 1. 이전 단계나 퀵버튼 클릭 등을 통해 명시적으로 의도가 미리 설정되어 들어왔다면 해당 의도를 즉시 유지합니다.
    current_intent = state.get("intent")
    if current_intent:
        return {"intent": current_intent}
        
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    input_clean = user_message = user_input.strip().lower()

    # 2. 온보딩 진행 체크 (Smart Bypass 예외)
    # - 만약 사용자가 현재 9단계 자소서 온보딩 문답을 진행 중(step 0~8)인 상태라면,
    # - 흐름을 방해하지 않고 자소서 작성 노드(resume_gen)로 강제 고정합니다.
    # - 단! 온보딩 중이라도 "검증", "피드백", "평가" 등의 명시적 키워드가 있는 경우는 온보딩 루프를 탈출하도록 예외 처리합니다.
    try:
        profile = get_user_profile(user_id)
        if profile is not None:
            step = profile.get("step", 0)
            # 온보딩 중간 단계인 경우 무조건 자소서 온보딩으로 강제 라우팅
            if 0 <= step < 9 and not any(k in input_clean for k in ["검증", "평가", "첨삭", "피드백", "판별"]):
                print(f"[Intent] 온보딩 진행 유저 확인 (현재 step: {step}) → 자소서 루프 강제 라우팅")
                return {"intent": "resume_gen"}
    except Exception as e:
        print(f"[Intent Warning] 온보딩 사전 확인 실패: {e}")

    # 3. 초고속 하드코딩 키워드 매칭 (LLM 호출 비용을 아끼고 빠른 응답을 위한 캐싱 필터)
    
    # 인사말 키워드가 포함되면 일반 일상챗으로 분류
    if any(k in input_clean for k in ["안녕", "누구", "반가워", "하이", "이름", "뭐해"]):
        return {"intent": "basic_chat"}

    # 자소서 검증/평가 요청 시 최우선 순위로 자소서 검증 노드로 라우팅
    if any(k in input_clean for k in ["검증", "평가", "첨삭", "피드백", "판별"]):
        return {"intent": "resume_verify"}
        
    # 일반 자소서/이력서 단어가 포함되면 자소서 작성 온보딩 노드로 라우팅
    if any(k in input_clean for k in ["이력서", "자기소개서", "자소서", "경력", "면접", "처음부터", "자소서 보여줘", "저장된 자소서"]):
        return {"intent": "resume_gen"}
        
    # 일자리 검색 키워드
    if any(k in input_clean for k in ["일자리", "알바", "취업", "구인", "공고", "일할", "채용", "추천"]):
        return {"intent": "job_search"}
        
    # 면접 및 구직 가이드 팁 요청 키워드
    if any(k in input_clean for k in ["가이드", "방법", "준비", "팁", "어떻게"]):
        return {"intent": "apply_guide"}

    # 4. LLM 기반 의도 분류 (하드코딩 키워드로 걸러지지 않는 애매한 일상 발화 분류)
    # - 빠르고 비용이 저렴한 gpt-4o-mini(llm_fast) 모델을 활용하여 분류합니다.
    system_prompt = (
        "당신은 중장년층 구직자 지원 시스템의 의도 분석가입니다.\n"
        "아래 사용자 발화를 분류하여 다음 카테고리 단어 중 '오직 한 단어'로만 답변하십시오:\n"
        "(resume_gen, resume_verify, job_search, apply_guide, basic_chat)\n"
        "다른 서술어나 기호, 백틱(```) 등은 포함하지 마십시오."
    )
    
    try:
        response = await llm_fast.ainvoke(f"{system_prompt}\n\n사용자 발화: {user_input}")
        res_text = get_content(response)
        
        # 알파벳만 남기고 정규식으로 안전하게 청소
        cleaned_intent = re.sub(r'[^a-zA-Z_]', '', res_text)
        
        if cleaned_intent in IntentEnum.__members__:
            analyzed_intent = cleaned_intent
        else:
            analyzed_intent = "basic_chat"
    except Exception as e:
        print(f"[Intent LLM Error] 의도 분석 실패: {e}")
        analyzed_intent = "basic_chat"
        
    return {"intent": analyzed_intent}
