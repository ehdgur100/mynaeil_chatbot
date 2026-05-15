from state import AgentState
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from enum import Enum
import config
import database

# ========================================================
# 1. 의도 분류용 데이터 구조 정의
# ========================================================
class IntentEnum(str, Enum):
    policy_search = "policy_search"
    resume_gen = "resume_gen"
    job_search = "job_search"
    edu_recommend = "edu_recommend"
    basic_chat = "basic_chat"

# ========================================================
# 2. 멀티 LLM 팩토리 로직
# ========================================================
if config.ACTIVE_LLM == "gemini":
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", api_key=config.GEMINI_API_KEY)
else:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=config.OPENAI_API_KEY)

# ========================================================
# 3. 비동기(Async) 노드 정의
# ========================================================

async def analyze_intent(state: AgentState) -> Dict[str, Any]:
    """사용자 의도를 분석하는 라우터 노드"""
    print("[Node] analyze_intent 실행")
    
    current_intent = state.get("intent")
    if current_intent:
        return {"intent": current_intent}
        
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    
    # 초고속 키워드 라우팅 (Bypass)
    if any(k in user_input for k in ["안녕", "누구", "반가워", "하이", "이름", "뭐해"]): return {"intent": "basic_chat"}
    if any(k in user_input for k in ["지원", "정책", "급여", "돈", "수당", "실업", "제도"]): return {"intent": "policy_search"}
    if any(k in user_input for k in ["이력서", "자기소개서", "자소서", "경력", "면접"]): return {"intent": "resume_gen"}
    if any(k in user_input for k in ["일자리", "알바", "취업", "구인", "공고", "일할", "채용"]): return {"intent": "job_search"}
    if any(k in user_input for k in ["교육", "내일배움", "자격증", "학원", "배우", "훈련"]): return {"intent": "edu_recommend"}
    
    system_prompt = """당신은 40~60대 중장년층의 재취업을 돕는 '나의내일' 챗봇의 의도 분석가입니다.
사용자의 발화를 읽고 카테고리 영문명만 대답하세요 (policy_search, resume_gen, job_search, edu_recommend, basic_chat)."""
    
    try:
        response = await llm.ainvoke(f"{system_prompt}\n\n사용자 발화: {user_input}")
        res_text = response.content[0].get("text", "").strip() if isinstance(response.content, list) else response.content.strip()
        analyzed_intent = res_text if res_text in IntentEnum.__members__ else "basic_chat"
    except:
        analyzed_intent = "basic_chat"
        
    return {"intent": analyzed_intent}

async def policy_search(state: AgentState) -> Dict[str, Any]:
    """Supabase RAG 기반 정책 검색 노드"""
    print("[Node] policy_search 실행 (RAG)")
    user_input = state["messages"][-1].content
    
    try:
        # 1. Supabase에서 관련 문서 검색 (커스텀 함수 사용)
        docs = await database.search_documents(user_input, k=3)
        
        if docs:
            context = "\n\n".join([d.page_content for d in docs])
            system_prompt = f"""당신은 중장년층 지원 정책 전문가입니다. 아래 [참고 정보]만을 바탕으로 친절하게 답변하세요.
정보가 없다면 모른다고 정직하게 말하고, 관련 기관에 문의하도록 안내하세요.
반드시 2~3문장 이내로 짧게 핵심만 답변하세요.

[참고 정보]
{context}
"""
        else:
            system_prompt = "당신은 중장년층 취업 지원 전문가입니다. 정확한 정보가 없을 경우 고용센터 방문이나 고용보험 홈페이지를 안내하세요. 2문장 이내로 답변하세요."
        
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ])
        ai_response = response.content[0].get("text", "") if isinstance(response.content, list) else response.content
    except Exception as e:
        print(f"RAG 에러: {e}")
        ai_response = "죄송합니다. 정책 정보를 검색하는 도중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
        
    return {"messages": [AIMessage(content=ai_response)]}

async def basic_chat(state: AgentState) -> Dict[str, Any]:
    """일반 대화 노드"""
    print("[Node] basic_chat 실행")
    user_input = state["messages"][-1].content
    
    # 인사말 키워드 → LLM 없이 즉시 응답 (타임아웃 방지)
    GREETING_KEYWORDS = ["안녕", "하이", "반가워", "반갑", "hi", "hello"]
    if any(k in user_input.lower() for k in GREETING_KEYWORDS):
        return {"messages": [AIMessage(content="안녕하세요! 😊 중장년층 재취업 지원 챗봇 '나의내일'입니다.\n\n정책 정보, 이력서 작성, 일자리 찾기, 교육 추천 중 원하시는 걸 말씀해 주세요!")]}
    
    system_prompt = """당신은 40~60대 중장년층의 재취업을 돕는 '나의내일' 챗봇의 친절한 상담사입니다.
최대한 따뜻하고 이해하기 쉬운 말로 1~3문장 이내로 짧게 답변하세요."""
    
    try:
        response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
        ai_response = response.content[0].get("text", "") if isinstance(response.content, list) else response.content
    except:
        ai_response = "반갑습니다! 무엇을 도와드릴까요?"
        
    return {"messages": [AIMessage(content=ai_response)]}


# 나머지 노드들은 일단 간단히 유지 (추후 RAG 확장 가능)
async def resume_gen(state: AgentState) -> Dict[str, Any]:
    return {"messages": [AIMessage(content="이력서 작성을 도와드릴게요. 경력을 간단히 말씀해 주시겠어요?")]}

async def job_search(state: AgentState) -> Dict[str, Any]:
    return {"messages": [AIMessage(content="거주 지역과 희망 직종을 말씀해 주시면 일자리를 찾아봐 드릴게요.")]}

async def edu_recommend(state: AgentState) -> Dict[str, Any]:
    return {"messages": [AIMessage(content="내일배움카드로 수강 가능한 교육 과정을 추천해 드립니다.")]}
