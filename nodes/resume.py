import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import config


async def rag_review(user_id: str, resume_text: str) -> str:
    # TODO: 개발자 4번 RAG 검증 AI 연결 예정
    return resume_text


_SECTION_LABELS = ["성장과정", "지원동기", "직무 경험 및 강점", "입사 후 포부"]

_SYSTEM_PROMPT = """당신은 5060세대 신중년 구직자의
자기소개서 작성을 돕는 전문 취업 컨설턴트입니다.

## 작성 전 반드시 아래 순서로 분석하세요
1. 지원자의 핵심 경력에서 강점 3가지를 파악하세요.
2. 뿌듯했던 경험과 힘든 극복 경험에서
   공통된 특성(예: 책임감, 끈기)을 찾으세요.
3. 지원 직무와 지원자 강점의 연결고리를 찾으세요.
4. 위 분석을 바탕으로 각 항목을 작성하세요.

## 작성 원칙
1. 추상적인 표현 대신 구체적인 숫자와 경험을 써주세요.
2. 문장은 짧고 명확하게 작성하세요.
3. 각 항목은 반드시 500자 이내로 작성하세요.
4. 50~60대 구직자의 강점인 성실함, 책임감,
   풍부한 경험을 자연스럽게 녹여주세요.

## 좋은 예시와 나쁜 예시

[나쁜 예시 - 절대 사용 금지]
"저는 성실하고 책임감이 강한 사람입니다.
열심히 일하겠습니다."

[좋은 예시 - 이 스타일로 작성]
"20년간 자동차 부품 공장에서 하루 500개 부품을
검수하며 불량률 0%를 유지했습니다.
팀 내 최다 근속자로 후배 3명을 직접 교육했습니다."

## 출력 형식
반드시 아래 형식으로만 출력하세요.

[성장과정]
내용

[지원동기]
내용

[직무 경험 및 강점]
내용

[입사 후 포부]
내용"""

_USER_TEMPLATE = """아래 지원자 정보를 바탕으로 자기소개서를 작성해주세요.

[지원자 정보]
- 핵심 경력: {career}
- 보유 자격증 및 기술: {skills}
- 희망 직무: {desired_job}
- 근무 희망 지역: {location}
- 근무 조건: {work_condition}
- 핵심 강점: {strengths}
- 최우선 목표: {goal}
- 뿌듯했던 경험: {proud_experience}
- 힘들었던 경험과 극복: {hardship}"""


_REVISION_SYSTEM_PROMPT = """당신은 자기소개서 수정을 돕는 전문 취업 컨설턴트입니다.
기존 자기소개서를 사용자의 요청에 맞게 수정해주세요.
수정하지 않는 항목은 그대로 유지하고,
반드시 아래 형식으로 출력하세요.

[성장과정]
내용

[지원동기]
내용

[직무 경험 및 강점]
내용

[입사 후 포부]
내용"""


async def revise_resume(
    existing_content: str, user_request: str, user_data: dict
) -> str:
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=config.OPENAI_API_KEY)
    user_prompt = (
        f"기존 자기소개서:\n{existing_content}\n\n"
        f"지원자 정보:\n"
        f"- 핵심 경력: {user_data.get('career') or ''}\n"
        f"- 보유 자격증 및 기술: {user_data.get('skills') or ''}\n"
        f"- 희망 직무: {user_data.get('desired_job') or ''}\n"
        f"- 근무 희망 지역: {user_data.get('location') or ''}\n"
        f"- 근무 조건: {user_data.get('work_condition') or ''}\n"
        f"- 핵심 강점: {user_data.get('strengths') or ''}\n"
        f"- 최우선 목표: {user_data.get('goal') or ''}\n"
        f"- 뿌듯했던 경험: {user_data.get('proud_experience') or ''}\n"
        f"- 힘들었던 경험과 극복: {user_data.get('hardship') or ''}\n\n"
        f"수정 요청:\n{user_request}\n\n"
        f"위 지원자 정보를 참고해서 수정 요청을 반영해줘.\n"
        f"수정하지 않는 항목은 그대로 유지해줘."
    )
    response = await llm.ainvoke(
        [
            SystemMessage(content=_REVISION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
    )
    return response.content


async def generate_resume(user_data: dict) -> str:
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=config.OPENAI_API_KEY)
    user_prompt = _USER_TEMPLATE.format(
        career=user_data.get("career") or "",
        skills=user_data.get("skills") or "",
        desired_job=user_data.get("desired_job") or "",
        location=user_data.get("location") or "",
        work_condition=user_data.get("work_condition") or "",
        strengths=user_data.get("strengths") or "",
        goal=user_data.get("goal") or "",
        proud_experience=user_data.get("proud_experience") or "",
        hardship=user_data.get("hardship") or "",
    )
    response = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
    )
    return response.content


def truncate_section(text: str, max_len: int = 500) -> str:
    """500자 초과 시 마지막 문장 끝에서 자르고 '...' 추가."""
    if len(text) <= max_len:
        return text

    chunk = text[:max_len]
    half = max_len // 2

    # 1순위: 마침표
    pos = chunk.rfind(".")
    if pos >= half:
        return chunk[: pos + 1] + "..."

    # 2순위: '요' 또는 '다' 뒤에 공백·줄바꿈·끝
    for i in range(len(chunk) - 1, half - 1, -1):
        if chunk[i] in ("요", "다") and (
            i == len(chunk) - 1 or chunk[i + 1] in (" ", "\n", ".")
        ):
            return chunk[: i + 1] + "..."

    # 3순위: 줄바꿈
    pos = chunk.rfind("\n")
    if pos >= half:
        return chunk[:pos].rstrip() + "..."

    # 최후: 강제 절단
    return chunk.rstrip() + "..."


def split_resume(resume_text: str) -> list[str]:
    """[섹션명] 기준으로 텍스트를 분리해 4개 항목 내용 반환 (각 항목 500자 제한)."""
    pattern = r"(\[성장과정\]|\[지원동기\]|\[직무 경험 및 강점\]|\[입사 후 포부\])"
    tokens = re.split(pattern, resume_text)

    content_map: dict[str, str] = {}
    for i, token in enumerate(tokens):
        clean = token.strip()
        if clean in (
            "[성장과정]",
            "[지원동기]",
            "[직무 경험 및 강점]",
            "[입사 후 포부]",
        ):
            label = clean[1:-1]
            content_map[label] = tokens[i + 1].strip() if i + 1 < len(tokens) else ""

    return [truncate_section(content_map.get(label, "")) for label in _SECTION_LABELS]


def build_resume_callback_response(sections: list[str]) -> dict:
    """4개 항목을 말풍선 2개로 묶은 카카오 콜백 응답 반환."""
    total = len(_SECTION_LABELS)
    bubble1 = "\n\n".join(
        f"📌 {i + 1}/{total} {_SECTION_LABELS[i]}\n{sections[i]}" for i in range(2)
    )
    bubble2 = "\n\n".join(
        f"📌 {i + 1}/{total} {_SECTION_LABELS[i]}\n{sections[i]}" for i in range(2, 4)
    )
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": bubble1}},
                {"simpleText": {"text": bubble2}},
            ]
        },
    }


_YOUTUBE_TIPS_CONTEXT = """
[면접왕 이형의 조언]
자기소개서 성장과정이나 직무 경험을 쓸 때는 '열심히 하겠다', '성실하다' 같은 추상적인 표현은 피하십시오. 대신 STAR 기법(상황, 과제, 행동, 결과)을 적용해 '어떤 상황에서 어떤 행동을 해서 수치적으로 무슨 성과를 냈다'로 명확하고 구체적으로 적어야 신뢰감을 줍니다.

[인사담당자 채널의 조언]
중장년층 구직자들의 가장 큰 무기는 풍부한 실무 경험과 위기 대응력입니다. 자소서 지원동기 부분에는 내가 과거에 어려운 한계 상황을 어떻게 노련한 책임감으로 극복했는지 구체적인 에피소드를 녹여내는 것이 인사담당자들의 눈길을 끄는 비결입니다.

[면접관 제이의 조언]
입사 후 포부를 작성할 때 단순히 '뼈를 묻겠다'는 식의 무조건적인 충성 맹세는 감점 요인입니다. 그보다는 '나의 과거 직무 경험과 회사의 현재 비즈니스 과제를 매칭하여, 1년 내에 이 직무에서 구체적으로 어떤 기여를 할 것인지' 기여 중심의 구체적 목표를 제시해야 합니다.
"""


async def generate_resume_with_tips(user_data: dict, additional_context: str = "") -> str:
    """유튜브 인사담당자들의 조언을 100% 반영하여 최종 완성된 자기소개서를 생성 및 수정합니다."""
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=config.OPENAI_API_KEY)
    
    system_prompt = """당신은 5060세대 신중년 구직자의 자기소개서 작성을 돕는 전문 취업 컨설턴트입니다.
제공된 [인사담당자들의 조언]을 참고하여, 지원자의 정보를 가장 돋보이게 다듬은 완성본 자기소개서를 직접 작성해 주세요.

작성 및 첨삭 원칙:
1. 제공된 [인사담당자들의 조언](STAR 기법 수치화 성과, 신중년 위기대응 에피소드, 기여 중심 구체적 포부)이 자소서 본문에 100% 완벽히 자연스럽게 녹아들어 첨삭이 완성되도록 작성하십시오.
2. 최종 자소서 텍스트에는 분석용 메타 태그나 유튜브 출처 텍스트를 본문에 절대 포함하지 마십시오. 오직 즉시 제출 가능한 순수 자기소개서 텍스트만 작성해야 합니다.
3. 각 항목은 반드시 500자 이내의 친절하고 따뜻한 해요체 문장으로 작성해 주세요.

출력 형식:
반드시 아래 형식으로만 출력하세요. 다른 인사말이나 잡설은 적지 마십시오.

[성장과정]
내용

[지원동기]
내용

[직무 경험 및 강점]
내용

[입사 후 포부]
내용"""

    user_prompt = f"""아래 지원자 정보와 조언을 바탕으로 완성도 높은 자소서를 작성해 주세요.

[지원자 정보]
- 핵심 경력: {user_data.get("career") or ""}
- 보유 자격증 및 기술: {user_data.get("skills") or ""}
- 희망 직무: {user_data.get("desired_job") or ""}
- 근무 희망 지역: {user_data.get("location") or ""}
- 근무 조건: {user_data.get("work_condition") or ""}
- 핵심 강점: {user_data.get("strengths") or ""}
- 최우선 목표: {user_data.get("goal") or ""}
- 뿌듯했던 경험: {user_data.get("proud_experience") or ""}
- 힘들었던 경험과 극복: {user_data.get("hardship") or ""}

[인사담당자들의 조언]
{_YOUTUBE_TIPS_CONTEXT}

{additional_context}"""

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return response.content
