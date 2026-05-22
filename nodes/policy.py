from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_smart, get_content
from database.vector_search import search_documents

async def policy_search(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 B 담당] Supabase pgvector RAG 기반 정부 지원 정책 및 자금 정보 검색 노드
    """
    print("[Node] policy_search 실행 (RAG)")
    user_input = state["messages"][-1].content if state.get("messages") else ""
    
    try:
        # 1. Supabase vector_search 모듈을 활용한 정책 문서 검색
        docs = await search_documents(user_input, k=3)
        
        if docs:
            context = "\n\n".join([f"관련 정책 정보: {d.page_content}" for d in docs])
            system_prompt = f"""당신은 중장년층(5060세대) 대상 고용 안정 및 창업/재취업 정부 지원 정책 전문가입니다.
아래 제공된 [참고 정보]만을 온전히 바탕으로 질문에 친절하고 상세하게 답변해 주세요.

작성 원칙:
1. 제공된 정보에 없는 가상의 내용을 지어내지 마십시오.
2. 정보가 충분하지 않거나 답변하기 곤란한 경우, 거주지 인근 고용센터 또는 고용노동부 콜센터(1350)로 직접 문의하도록 안내하세요.
3. 중장년층이 읽기 쉽도록 친절하고 격려하는 해요체 어조를 활용하십시오.
4. 너무 길어지지 않게 핵심 내용을 3~4문장 이내로 정리하세요.

[참고 정보]
{context}
"""
        else:
            system_prompt = (
                "당신은 중장년층 고용 및 취업 지원 전문가입니다. "
                "질문과 정확히 매칭되는 데이터베이스 내 지원 정책이 존재하지 않습니다. "
                "대신 거주지 인근 고용복지플러스센터나 고용보험 홈페이지(www.ei.go.kr)를 "
                "방문하여 직접 1:1 상담을 받아보실 것을 권장하는 안내 답변을 작성해 주세요. "
                "따뜻한 해요체 어조로 2문장 이내로 작성하십시오."
            )
        
        # 2. LLM 호출
        response = await llm_smart.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ])
        ai_response = get_content(response)
    except Exception as e:
        print(f"[Policy Error] RAG 정책 검색 중 에러 발생: {e}")
        ai_response = "죄송합니다. 정책 정보를 검색하는 도중 오류가 발생했습니다. 잠시 후 다시 검색해 주세요. 😥"
        
    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": ai_response}}]}
        },
        "intent": "policy_search"
    }
