from typing import Dict, Any
from state import AgentState
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_smart, get_content
import database.operations as db_ops
import config

# ==========================================
# 1. [팀원] 개별 공고 지원 가이드 생성 로직
# ==========================================
_SYSTEM_PROMPT = """당신은 50~60대 신중년 구직자의 취업을 돕는
친절한 취업 도우미입니다.

아래 공고 정보를 바탕으로 지원 방법을 파악하고,
처음 지원하는 분도 따라할 수 있도록
단계별로 안내해주세요.

안내 원칙:
1. 최대한 쉽고 친절하게 설명해주세요.
2. 이메일, 홈페이지, 방문, 전화 중
   어떤 방식인지 먼저 파악하세요.
3. 지원에 필요한 구체적인 정보
   (이메일 주소, URL, 전화번호 등)를
   공고에서 찾아서 포함해주세요.
4. 지원 방법을 파악할 수 없으면
   공고 원문 링크를 안내해주세요.
5. 문장은 짧고 명확하게 써주세요.

출력 형식:
📋 지원 방법 안내

[지원 방식] 이메일/홈페이지/방문/전화 접수

1단계. 내용
2단계. 내용
3단계. 내용
...

📌 공고 원문: {source_url}"""

_USER_TEMPLATE = """아래 공고의 지원 방법을 안내해주세요.

[공고 정보]
- 회사명: {company}
- 직무: {title}
- 공고 내용: {description}
- 근무지: {location}
- 마감일: {deadline}
- 공고 원문 URL: {source_url}"""


async def get_apply_guide(job: dict) -> str:
    source_url = job.get("source_url") or "알 수 없음"
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=config.OPENAI_API_KEY)
    user_prompt = _USER_TEMPLATE.format(
        company=job.get("company") or "정보 없음",
        title=job.get("title") or "정보 없음",
        description=job.get("description") or "정보 없음",
        location=job.get("location") or "정보 없음",
        deadline=job.get("deadline") or "미정",
        source_url=source_url,
    )
    try:
        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        return response.content
    except Exception as e:
        print(f"[get_apply_guide] 오류: {e}")
        return (
            f"지원 방법 안내 중 오류가 발생했어요 😥\n"
            f"공고 원문을 직접 확인해 주세요.\n"
            f"👉 {source_url}"
        )


# ==========================================
# 2. [우리] 취업 코치 가이드 노드 로직
# ==========================================
_GUIDE_SYSTEM_PROMPT = """당신은 5060 신중년 구직자의 성공적인 취업을 돕는 1:1 취업 밀착 코치입니다.
사용자의 희망 직무 및 개인 정보를 참고하여 구체적이고 실질적인 구직 지원 가이드를 구성하세요.

가이드 구성 요소:
1. 직무별 필수/우대 조건 안내: (예: 경비·시설관리는 신임경비교육 이수증, 요양보호사는 요양보호사 자격증 필요 등)
2. 서류 지원 요령: 신중년 이력서 작성 시 가장 눈여겨보는 '신뢰와 경험'을 강조하는 방법.
3. 면접 대비 행동 강령: 면접 장소에서의 태도, 단정한 용모, 성실한 소통 자세 팁.
4. 오프라인 취업 지원 인프라 소개: 고용복지플러스센터, 중장년 내일센터 등 활용 방법.

작성 원칙:
- 만약 지원자의 희망 직무나 연령대 등의 프로필 정보가 제공된다면 그에 맞춰 철저히 맞춤형 가이드를 설계하십시오.
- 따뜻하고 신뢰감을 주는 존댓말(해요체)로 3~4개의 간결한 섹션으로 항목을 나누어 가독성 있게 표현하십시오.
"""

_GUIDE_USER_TEMPLATE = """아래는 지원자의 프로필 정보와 문의 사항입니다.

[지원자 프로필]
- 희망 직무: {desired_job}
- 보유 자격증/기술: {skills}
- 핵심 경력: {career}
- 희망 지역: {location}

[문의 사항]
{user_input}

지원자 맞춤형 취업 가이드를 구체적으로 작성해 주세요."""


async def apply_guide(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 B 담당] 구직 지원 가이드를 생성하는 노드.
    사용자의 프로필을 DB에서 읽어 직종별 맞춤형(경비교육, 요양자격증 등) 지원 팁과 가이드를 llm_smart로 생성합니다.
    """
    print("[Node] apply_guide 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    
    # 1. 유저 프로필 정보 가져와서 개인화
    profile = db_ops.get_user_profile(user_id) or {}
    
    desired_job = profile.get("desired_job", "미정")
    skills = profile.get("skills", "없음")
    career = profile.get("career", "기록 없음")
    location = profile.get("location", "전국")

    user_prompt = _GUIDE_USER_TEMPLATE.format(
        desired_job=desired_job,
        skills=skills,
        career=career,
        location=location,
        user_input=user_input
    )

    try:
        response = await llm_smart.ainvoke([
            SystemMessage(content=_GUIDE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ])
        ai_response = get_content(response)
    except Exception as e:
        print(f"[Guide Error] 가이드 생성 실패: {e}")
        ai_response = (
            "구직 가이드를 작성하는 도중 문제가 생겼습니다. 😥\n"
            "일반적으로 중장년 취업을 위해서는 희망 구직 직종에 필요한 요건(예: 요양보호사 자격증, 신임경비교육 등)을 "
            "먼저 갖추시고 고용센터에 구직등록을 하시는 것이 좋습니다."
        )

    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": ai_response}}]}
        },
        "intent": "apply_guide"
    }
