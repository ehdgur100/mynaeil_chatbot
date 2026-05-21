from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_fast
import database.operations as db_ops
from services.hrd_api import HRDNetAPIClient
import config

async def edu_recommend(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 A 담당] 국민내일배움카드로 수강 가능한 교육 과정을 매칭하고 추천해주는 노드.
    사용자의 희망 직무나 대화에서 교육 키워드를 추출하여 HRD-Net API 모듈과 연동합니다.
    """
    print("[Node] edu_recommend 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""

    # 1. 사용자 프로필 및 희망 직무 조회
    profile = db_ops.get_user_profile(user_id) or {}
    desired_job = profile.get("desired_job")

    # 2. 대화 본문 및 희망 직무를 통해 타겟 교육 분야(키워드) 추출 (llm_fast 사용)
    extract_prompt = (
        "사용자가 수강하고 싶어 하는 교육 주제나 직무 자격증 종류를 단어로 추출하십시오.\n"
        "예: '요양보호사 교육 과정이 있나요?' -> '요양보호사'\n"
        "예: '지게차 운전 배울 곳 없나?' -> '지게차'\n"
        "특별한 키워드가 보이지 않는다면, 사용자의 희망 직무를 바탕으로 추출하고, "
        "둘 다 알 수 없는 경우 오직 '재취업 일반'이라고 답변하세요.\n"
        "다른 군더더기 없이 딱 단어 한 개만 대답하세요."
    )
    
    user_context = f"사용자 입력: {user_input}\n사용자 희망직무: {desired_job or '알 수 없음'}"
    
    try:
        response = await llm_fast.ainvoke([
            SystemMessage(content=extract_prompt),
            HumanMessage(content=user_context)
        ])
        subject = response.content.strip()
    except Exception as e:
        print(f"[Edu Keyword Extract Error] {e}")
        subject = desired_job or "재취업 일반"

    # 3. HRD-Net API 클라이언트를 활용한 교육 검색 수행
    hrd_client = HRDNetAPIClient(auth_key=getattr(config, "HRD_API_KEY", ""))
    location = profile.get("location", "")
    
    try:
        courses = await hrd_client.get_training_courses(subject, location=location)
    except Exception as e:
        print(f"[HRD API Error] {e}")
        courses = []

    # 4. 추천 결과 포맷팅 및 응답 생성
    if courses:
        course_list_str = ""
        for i, c in enumerate(courses):
            course_list_str += (
                f"▪️ {c.get('title')}\n"
                f"  - 훈련기관: {c.get('institution')}\n"
                f"  - 기간: {c.get('duration')}\n"
                f"  - 국비지원: {c.get('support_type')}\n"
                f"  - 바로가기: {c.get('link')}\n\n"
            )
            
        ai_response = (
            f"요청하신 '{subject}' 분야의 모집 중인 내일배움카드 교육과정을 찾아보았어요! 🎓\n\n"
            f"{course_list_str.strip()}\n\n"
            f"💡 국민내일배움카드를 지참하여 HRD-Net 홈페이지에서 직접 수강 신청하실 수 있습니다. "
            f"더 많은 교육 과정 정보가 필요하시면 원하시는 주제와 지역을 말씀해 주세요!"
        )
    else:
        ai_response = (
            f"죄송합니다. 현재 '{subject}' 분야의 내일배움카드 모집중인 교육과정을 확인하지 못했어요. 😥\n\n"
            f"가까운 고용복지플러스센터나 HRD-Net 공식 홈페이지를 방문하시면 "
            f"수시로 개설되는 새로운 취업 특화 훈련들을 직접 찾아보실 수 있습니다."
        )

    # 5. Kakao톡 템플릿에 맞춤형 빠른답장 버튼 구성
    quick_replies = ["국민내일배움카드란?", "다른 교육 찾기", "자소서 작성하기"]
    kakao_resp = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": ai_response}}],
            "quickReplies": [
                {"action": "message", "label": label, "messageText": label}
                for label in quick_replies
            ]
        }
    }

    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": kakao_resp,
        "intent": "edu_recommend"
    }
