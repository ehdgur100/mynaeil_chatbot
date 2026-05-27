from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage
import database.operations as db_ops
from database.connection import supabase
import nodes.resume as resume

async def resume_verify(state: AgentState) -> Dict[str, Any]:
    """
    유튜브 인사담당자들의 3대 핵심 조언을 시스템 프롬프트 내부에서 참고하여
    사용자의 자기소개서를 최종 완성해주는 노드 (RAG 생략 최적화).
    """
    print("[Node] resume_verify 실행 (RAG 생략 최적화)")
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

    # 2. 내장된 꿀팁을 반영하여 자소서 최종 수정본 작성
    profile = db_ops.get_user_profile(user_id) or {}
    try:
        revised_resume = await resume.generate_resume_with_tips(
            profile, 
            f"기존 자소서 본문:\n{resume_content}\n\n위 기존 자소서를 분석하여 누락된 조언들을 마저 적용해 더 완성도 높은 자소서로 고쳐 써주세요."
        )
    except Exception as e:
        print(f"[Verify LLM Error] 자소서 수정 LLM 호출 실패: {e}")
        revised_resume = resume_content

    # 3. DB 저장 및 완료 상태 갱신
    db_ops.save_resume(user_id, desired_job, revised_resume)
    try:
        if supabase is not None:
            supabase.table("users").update({"resume_status": "done"}).eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[Verify Status Update Warning] resume_status 갱신 실패: {e}")

    # 4. 카카오톡 응답 구성 (수정 완료 자소서 2개 말풍선 + 안내문 1개)
    sections = resume.split_resume(revised_resume)
    kakao_response = resume.build_resume_callback_response(sections)
    
    msg = (
        "자기소개서가 완성되었습니다! 🎉\n"
        "인사담당자들의 최신 취업 조언을 반영하여 가장 설득력 있게 다듬은 완성본입니다. 😊"
    )
    kakao_response["template"]["outputs"].append({"simpleText": {"text": msg}})
    kakao_response["template"]["quickReplies"] = [
        {"action": "message", "label": "완료", "messageText": "완료"},
        {"action": "message", "label": "처음부터", "messageText": "처음부터"},
    ]

    return {
        "messages": [AIMessage(content=revised_resume)],
        "kakao_response": kakao_response,
        "intent": "resume_verify"
    }
