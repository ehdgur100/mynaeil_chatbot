from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage
import database.operations as db_ops
from database.vector_search import search_resume_tips
from database.connection import supabase
import nodes.resume as resume

async def resume_verify(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 A 담당] 유튜브 인사담당자 스크립트 RAG 검색을 통해
    사용자의 자기소개서를 보완 및 첨삭하여 최종 완성해주는 노드.
    """
    print("[Node] resume_verify 실행 (RAG)")
    user_id = state.get("user_id", "unknown")
    
    # 1. DB에 저장된 기존 자소서 불러오기
    saved = db_ops.get_resume(user_id)
    if not saved or not saved.get("content"):
        msg = (
            "검증할 자기소개서가 발견되지 않았습니다. 😥\n\n"
            "먼저 '자소서 작성' 메뉴를 통해 자기소개서를 작성해 주시면 "
            "유튜브 인사담당자들의 팁을 기반으로 꼼꼼히 첨삭 및 완성해 드릴게요!"
        )
        return {
            "messages": [AIMessage(content=msg)],
            "kakao_response": {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": msg}}]}
            },
            "intent": "resume_verify"
        }
        
    resume_content = saved["content"]
    desired_job = saved.get("desired_job", "")

    # 2. pgvector 비동기 RAG 검색 (유튜브 자소서 작성/면접 팁)
    try:
        docs = await search_resume_tips(resume_content, k=2)
    except Exception as e:
        print(f"[Verify RAG Error] youtube_tips 검색 실패: {e}")
        docs = []

    # 3. 조언 컨텍스트 구성
    if docs:
        context_parts = []
        for i, d in enumerate(docs):
            channel = d.metadata.get("channel_name", "인사담당자")
            context_parts.append(f"[{channel}의 조언]\n{d.page_content}")
        context = "\n\n".join(context_parts)
    else:
        context = "일반적인 취업 모범 사례를 기준으로 검증하여 자소서를 보완하십시오."

    # 4. RAG 조언을 바탕으로 자소서를 즉시 재작성/수정하는 LLM 호출
    # 사용자의 전체 답변 프로필을 조회하여 자소서 작성의 일관성을 높입니다.
    profile = db_ops.get_user_profile(user_id) or {}
    try:
        revised_resume = await resume.generate_resume_with_tips(
            profile, 
            f"기존 자소서 본문:\n{resume_content}\n\n[적용할 인사담당자들의 조언]\n{context}"
        )
    except Exception as e:
        print(f"[Verify LLM Error] 자소서 수정 LLM 호출 실패: {e}")
        revised_resume = resume_content

    # 5. DB 저장 및 완료 상태 갱신
    db_ops.save_resume(user_id, desired_job, revised_resume)
    try:
        if supabase is not None:
            supabase.table("users").update({"resume_status": "done"}).eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[Verify Status Update Warning] resume_status 갱신 실패: {e}")

    # 6. 카카오톡 응답 구성 (자소서 2개 말풍선 + 수정 완료 안내 말풍선 1개)
    sections = resume.split_resume(revised_resume)
    kakao_response = resume.build_resume_callback_response(sections)
    
    completion_msg = (
        "자기소개서가 완성되었습니다! 🎉\n"
        "인사담당자들의 최신 취업 조언을 반영하여 가장 설득력 있게 다듬은 완성본입니다. 😊\n\n"
        "혹시 수정하고 싶으신 부분이 있다면 아래에 편하게 말씀해 주세요 (예: '성격 부분 강조해줘')."
    )
    kakao_response["template"]["outputs"].append({"simpleText": {"text": completion_msg}})
    kakao_response["template"]["quickReplies"] = [
        {"action": "message", "label": "완료", "messageText": "완료"},
        {"action": "message", "label": "처음부터", "messageText": "처음부터"}
    ]

    return {
        "messages": [AIMessage(content=revised_resume)],
        "kakao_response": kakao_response,
        "intent": "resume_verify"
    }
