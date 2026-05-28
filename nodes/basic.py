from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from nodes.base import get_content, llm_fast
from nodes.navigation import is_home_request, main_menu_response
from state import AgentState
from database.connection import supabase


MAIN_QUICK_REPLIES = [
    ("📝 자기소개서 작성", "자기소개서 작성"),
    ("💼 일자리 검색", "일자리 검색"),
    ("🎓 교육 추천", "교육 추천"),
]


def _kakao_text_response(text: str) -> dict[str, Any]:
    return main_menu_response(text)


def _reset_active_flow(user_id: str) -> None:
    if supabase is None:
        return
    try:
        supabase.table("users").update(
            {"step": 0, "resume_status": "none", "selected_job_id": None}
        ).eq("user_id", user_id).execute()
    except Exception as exc:
        print(f"[Basic Navigation Reset Warning] {exc}")


async def basic_chat(state: AgentState) -> Dict[str, Any]:
    print("[Node] basic_chat 실행")
    user_id = state.get("user_id", "unknown")
    user_input = state["messages"][-1].content if state.get("messages") else ""
    lowered = user_input.lower()

    greeting_keywords = ["안녕", "하이", "반가", "hi", "hello", "소개", "이름"]
    if is_home_request(user_input):
        _reset_active_flow(user_id)
        text = (
            "처음 화면으로 돌아왔어요. 😊\n\n"
            "아래 메뉴 중 필요한 기능을 선택해주세요.\n\n"
            "📝 자기소개서 작성\n"
            "💼 일자리 검색\n"
            "🎓 교육 추천"
        )
        return {
            "messages": [AIMessage(content=text)],
            "kakao_response": _kakao_text_response(text),
            "intent": "basic_chat",
        }

    if any(keyword in lowered for keyword in greeting_keywords):
        text = (
            "안녕하세요. 5060 중장년의 구직과 교육 준비를 돕는 "
            "나의내일 챗봇입니다. 😊\n\n"
            "아래 메뉴 중 필요한 기능을 선택해주세요.\n\n"
            "📝 자기소개서 작성\n"
            "💼 일자리 검색\n"
            "🎓 교육 추천"
        )
        return {
            "messages": [AIMessage(content=text)],
            "kakao_response": _kakao_text_response(text),
            "intent": "basic_chat",
        }

    system_prompt = (
        "당신은 5060 중장년 구직자를 돕는 친절한 상담자입니다. "
        "사용자의 질문에 2~3문장 이내로 답하고, 필요하면 자기소개서 작성, "
        "일자리 검색, 교육 추천 기능을 안내하세요."
    )

    try:
        response = await llm_fast.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input),
            ]
        )
        text = get_content(response)
    except Exception as exc:
        print(f"[Basic Chat Error] {exc}")
        text = "무엇을 도와드릴까요? 📝 자기소개서 작성, 💼 일자리 검색, 🎓 교육 추천 중에서 선택해주세요."

    return {
        "messages": [AIMessage(content=text)],
        "kakao_response": _kakao_text_response(text),
        "intent": "basic_chat",
    }
