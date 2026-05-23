from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_fast, get_content

async def basic_chat(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 A 담당] 사용자 편의 및 자연스러운 소통을 돕는 일반 일상 대화 안내 노드.
    인사말 등은 LLM을 거치지 않고 캐싱 룰에 따라 초고속 즉시 답변을 수행해 응답 속도를 높입니다.
    """
    print("[Node] basic_chat 실행")
    user_input = state["messages"][-1].content if state.get("messages") else ""
    
    # 1. 인사말 및 단순 환영 유도용 즉시 응답 룰 (API 비용 및 지연 단축)
    GREETING_KEYWORDS = ["안녕", "하이", "반가워", "반갑", "hi", "hello", "누구", "소개", "이름"]
    if any(k in user_input.lower() for k in GREETING_KEYWORDS):
        welcome_msg = (
            "안녕하세요! 😊 5060 신중년 재취업 동반자 '나의내일' 챗봇입니다.\n\n"
            "저는 구직자 맞춤형 일자리 찾기와 자기소개서 완성을 도와드릴 수 있어요. 아래 중 원하시는 서비스를 선택해 주세요!\n\n"
            "✍️ 내 경험을 담은 '자기소개서 작성'\n"
            "🔍 내게 맞는 '일자리 검색'"
        )
        quick_replies = ["자소서 작성", "일자리 검색"]
        return {
            "messages": [AIMessage(content=welcome_msg)],
            "kakao_response": {
                "version": "2.0",
                "template": {
                    "outputs": [{"simpleText": {"text": welcome_msg}}],
                    "quickReplies": [
                        {"action": "message", "label": label, "messageText": label}
                        for label in quick_replies
                    ]
                }
            },
            "intent": "basic_chat"
        }
        
    # 2. 캐시 룰에 걸리지 않는 범용 일상 대화는 llm_fast를 활용해 대답
    system_prompt = """당신은 5060세대 중장년층의 제2의 인생 설계를 돕는 따뜻하고 살가운 상담원입니다.
사용자의 질문에 친절하게 2~3문장 이내로 답변하세요.
지원되지 않는 복잡한 기술적 문제나 업무 처리에 대해서는 '나의내일'의 핵심 서비스(자소서 작성, 일자리 찾기)를 다시 안내하며 유도하세요.
"""
    
    try:
        response = await llm_fast.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ])
        ai_response = get_content(response)
    except Exception as e:
        print(f"[Basic Chat Error] {e}")
        ai_response = "무슨 말씀인지 잘 이해하지 못했어요. 자소서 작성, 일자리 검색 중 어떤 걸 도와드릴까요?"
 
    quick_replies = ["자소서 작성", "일자리 검색"]
    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": ai_response}}],
                "quickReplies": [
                    {"action": "message", "label": label, "messageText": label}
                    for label in quick_replies
                ]
            }
        },
        "intent": "basic_chat"
    }
