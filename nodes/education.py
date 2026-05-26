import json
import re
from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_fast, get_content
import database.operations as db_ops
import config

async def edu_recommend(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 A 담당] 국민내일배움카드로 수강 가능한 교육 과정을 매칭하고 추천해주는 노드.
    사용자와의 대화 문맥에서 희망 '교육 분야'와 '지역'을 파악한 후 Supabase education 테이블에서 검색합니다.
    """
    print("[Node] edu_recommend 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    
    # 1. 최근 3개의 사용자 발화를 모아 대화 문맥 구성
    recent_messages = [m for m in messages if isinstance(m, HumanMessage)][-3:]
    chat_history = "\n".join([f"User: {m.content}" for m in recent_messages]) if recent_messages else ""

    # 2. LLM을 사용하여 대화 내역에서 교육 키워드와 지역 추출
    extract_prompt = (
        "사용자의 최근 대화 내역을 분석하여, 사용자가 찾고 있는 '교육 분야(키워드)'와 '희망 지역'을 JSON으로 추출하세요.\n"
        "예시: '마포구 요양보호사 교육' -> {\"keyword\": \"요양보호사\", \"location\": \"마포구\"}\n"
        "예시: '국비교육 추천' -> {\"keyword\": \"\", \"location\": \"\"}\n"
        "아직 대화에서 명확히 언급되지 않은 항목은 빈 문자열(\"\")로 두세요.\n"
        "반드시 JSON 형태로만 응답하고 백틱(```) 등은 포함하지 마십시오."
    )
    
    try:
        response = await llm_fast.ainvoke([
            SystemMessage(content=extract_prompt),
            HumanMessage(content=chat_history)
        ])
        content_val = response.content
        if isinstance(content_val, list):
            content_str = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content_val])
        else:
            content_str = str(content_val)

        # JSON 텍스트 추출
        cleaned = re.search(r'\{.*\}', content_str.strip(), re.DOTALL)
        if cleaned:
            extracted = json.loads(cleaned.group(0))
        else:
            extracted = {"keyword": "", "location": ""}
    except Exception as e:
        print(f"[Edu Keyword Extract Error] {e}")
        extracted = {"keyword": "", "location": ""}

    keyword = extracted.get("keyword", "").strip()
    location = extracted.get("location", "").strip()

    # 3. 정보 부족 시 질문 던지기 (QnA 플로우)
    if not keyword or not location:
        if not keyword and not location:
            ask_msg = "어떤 직무 분야의 교육을 원하시나요? (예: 바리스타, 컴퓨터 등)\n그리고 원하시는 수강 지역(시/구)도 함께 말씀해 주세요! 🏫"
        elif not keyword:
            ask_msg = f"지역은 '{location}'이시군요!\n어떤 분야의 교육을 받고 싶으신가요? (예: 요양보호사, 제과제빵 등)"
        else:
            ask_msg = f"'{keyword}' 교육을 찾으시는군요!\n원하시는 수강 지역(시/구)은 어디신가요?"
            
        kakao_resp = {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": ask_msg}}]
            }
        }
        return {
            "messages": [AIMessage(content=ask_msg)],
            "kakao_response": kakao_resp,
            "intent": "edu_recommend"  # 다음 턴에도 이 노드로 들어오게 유지
        }

    # 4. 정보가 충분하면 Supabase education 테이블 검색
    courses = db_ops.search_education(keyword, location, limit=5)

    # 5. 카카오 캐러셀 응답 포맷팅
    if courses:
        items = []
        for c in courses:
            title = c.get('title') or "교육명 미상"
            provider = c.get('provider') or "기관 미상"
            edu_loc = c.get('education_location') or location
            fee = c.get('fee_text') or "비용 정보 없음"
            link = c.get('application_url') or c.get('source_url') or "https://www.hrd.go.kr"
            
            similarity = c.get('similarity')
            
            # 카드 설명란 텍스트 구성
            desc = ""
            if similarity is not None:
                match_percent = int(similarity * 100)
                desc += f"[💡매칭률: {match_percent}%]\n"
            desc += f"🏢 기관: {provider}\n📍 장소: {edu_loc}\n💰 비용: {fee}"
            
            item = {
                "title": title,
                "description": desc,
                "buttons": [
                    {
                        "action": "webLink",
                        "label": "자세히 보기",
                        "webLinkUrl": link
                    }
                ]
            }
            items.append(item)
            
        ai_response_text = f"요청하신 '{location}' 지역의 '{keyword}' 관련 훈련/교육 추천 목록입니다! 🎓\n자세히 보기를 클릭하시면 신청 페이지로 이동합니다."
        kakao_resp = {
            "version": "2.0",
            "template": {
                "outputs": [
                    {"simpleText": {"text": ai_response_text}},
                    {
                        "carousel": {
                            "type": "basicCard",
                            "items": items
                        }
                    }
                ],
                "quickReplies": [
                    {"action": "message", "label": "다른 교육 찾기", "messageText": "국비교육 추천"},
                    {"action": "message", "label": "일자리 검색", "messageText": "일자리 검색"}
                ]
            }
        }
        ai_response = AIMessage(content=ai_response_text)
    else:
        ai_response_text = f"죄송합니다. 현재 '{location}' 지역에 '{keyword}' 관련 모집 중인 훈련/교육 과정이 없습니다. 😥\n다른 분야나 지역으로 다시 검색해 보시겠어요?"
        ai_response = AIMessage(content=ai_response_text)
        kakao_resp = {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": ai_response_text}}],
                "quickReplies": [
                    {"action": "message", "label": "다른 교육 찾기", "messageText": "국비교육 추천"},
                    {"action": "message", "label": "자소서 작성", "messageText": "자소서 작성"}
                ]
            }
        }

    return {
        "messages": [ai_response],
        "kakao_response": kakao_resp,
        "intent": "edu_recommend"
    }
