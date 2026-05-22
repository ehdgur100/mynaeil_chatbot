from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_smart, get_content
import database.operations as db_ops
from database.vector_search import search_resume_tips

_VERIFY_SYSTEM_PROMPT = """당신은 신중년(5060세대) 구직자의 자기소개서를 전문적으로 검증하고 피드백을 제공하는 베테랑 취업 컨설턴트입니다.
제공된 [인사담당자들의 조언]을 바탕으로, 지원자의 [자기소개서]를 다음 기준에 맞춰 정밀하게 검증해 주세요.

검증 기준:
1. 표면적 내용 평가: 구체적인 경험과 수치적 성과가 들어가 있는가? 추상적인 표현(예: '열심히 하겠다', '성실하다', '뼈를 묻겠다')은 무엇이고 어떻게 개선할 수 있는가?
2. 이면적 태도 검증: 신중년의 강점(책임감, 성실함, 노련함)이 잘 살아있으면서도, 과거에 안주하거나 변화를 거부하는 수동적인 태도가 보이지 않는가?
3. 구체적인 개선 제안: 피드백으로 그치지 말고, 어떻게 수정해야 하는지 구체적인 비포(Before) & 애프터(After) 작성 구절 예시를 함께 보여주세요.

출력 원칙:
- 반드시 검색된 참고 정보의 출처 채널명("[OOO 인사담당자 팁에 따르면~]", "[OOO 채널의 조언에 의하면~]" 등)을 명시적으로 본문에 언급하며 신뢰도 높은 피드백을 구성하세요.
- 친절하고 따뜻한 어조(해요체)를 사용하되, 구직에 도움이 될 수 있도록 뼈아픈 조언도 솔직하게 제시하세요.
- 총 3~4개의 핵심 피드백 포인트를 마크다운 형식을 사용하여 깔끔하게 정리해 주세요.
"""

_VERIFY_USER_TEMPLATE = """아래는 지원자의 자기소개서 내용과 관련 인사담당자들의 피드백 정보입니다.

[참고 정보 (인사담당자 조언)]
{context}

[검증 대상 자기소개서]
{resume_content}

위의 자기소개서를 정밀 분석하고, [인사담당자 조언]에 부합하도록 개선 피드백을 작성해 주세요."""

async def resume_verify(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 A 담당] 유튜브 인사담당자 스크립트 RAG 검색을 통해
    사용자의 자기소개서를 정밀하게 검증 및 피드백해주는 노드.
    """
    print("[Node] resume_verify 실행 (RAG)")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    stripped = user_input.strip()

    # 1. 검증할 자기소개서 내용 식별
    resume_content = ""
    
    # 만약 유저가 장문의 텍스트를 직접 입력했다면 이를 검증 대상으로 삼음
    if len(stripped) > 80 and not any(k in stripped for k in ["검증", "평가", "피드백", "자소서 보여줘"]):
        resume_content = stripped
        print("[Verify] 유저가 입력한 직접 입력 텍스트를 검증합니다.")
    else:
        # 그렇지 않으면 DB에 저장된 자소서가 있는지 확인
        saved = db_ops.get_resume(user_id)
        if saved:
            resume_content = saved.get("content", "")
            print("[Verify] DB에 저장된 유저의 자소서를 불러와 검증합니다.")
        
    # 검증할 자소서가 전혀 없는 경우 안내 처리
    if not resume_content:
        msg = (
            "검증할 자기소개서가 발견되지 않았습니다. 😥\n\n"
            "자기소개서를 먼저 작성해주시거나, 검증받고 싶은 자기소개서 텍스트(80자 이상)를 "
            "이 채팅방에 직접 입력해 주시면 유튜브 인사담당자들의 팁을 기반으로 꼼꼼히 분석해 드릴게요!"
        )
        return {
            "messages": [AIMessage(content=msg)],
            "kakao_response": {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": msg}}]}
            },
            "intent": "resume_verify"
        }

    # 2. pgvector 비동기 RAG 검색 (유튜브 자소서 작성/면접 팁)
    try:
        docs = await search_resume_tips(resume_content, k=3)
    except Exception as e:
        print(f"[Verify RAG Error] youtube_tips 검색 실패: {e}")
        docs = []

    # 3. 프롬프트 구성 및 LLM 호출 (llm_smart 활용)
    if docs:
        context_parts = []
        for i, d in enumerate(docs):
            channel = d.metadata.get("channel_name", "인사담당자")
            context_parts.append(f"[{i+1}] 채널명: {channel}\n조언내용: {d.page_content}")
        context = "\n\n".join(context_parts)
    else:
        context = "관련 유튜버 조언 팁 정보가 데이터베이스에 존재하지 않습니다. 일반적인 취업 모범 사례를 기준으로 검증하십시오."

    user_prompt = _VERIFY_USER_TEMPLATE.format(
        context=context,
        resume_content=resume_content
    )

    try:
        response = await llm_smart.ainvoke([
            SystemMessage(content=_VERIFY_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ])
        ai_response = get_content(response)
    except Exception as e:
        print(f"[Verify LLM Error] 자소서 검증 LLM 호출 실패: {e}")
        ai_response = "죄송합니다. 자기소개서를 검증하는 프로세스 중 예상치 못한 에러가 발생했습니다."

    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": ai_response}}]}
        },
        "intent": "resume_verify"
    }
