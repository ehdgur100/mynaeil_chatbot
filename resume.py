import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import config

_SECTION_LABELS = ["성장과정", "지원동기", "직무 경험 및 강점", "입사 후 포부"]

_SYSTEM_PROMPT = """당신은 5060세대 신중년 구직자의 자기소개서 작성을 돕는 전문 취업 컨설턴트입니다.
사용자가 제공한 경력과 강점을 바탕으로 자기소개서를 작성해주세요.

작성 원칙:
1. 문장은 짧고 명확하게 작성하세요.
2. 추상적인 표현 대신 구체적인 경험과 숫자를 활용하세요.
3. 50~60대 구직자의 강점인 성실함, 책임감, 풍부한 경험을 자연스럽게 녹여주세요.
4. 반드시 아래 형식으로 항목을 구분해서 출력하세요.
5. 각 항목은 반드시 500자 이내로 작성하세요.

출력 형식:
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
- 최우선 목표: {goal}"""


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
    )
    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
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
        return chunk[:pos + 1] + "..."

    # 2순위: '요' 또는 '다' 뒤에 공백·줄바꿈·끝
    for i in range(len(chunk) - 1, half - 1, -1):
        if chunk[i] in ("요", "다") and (
            i == len(chunk) - 1 or chunk[i + 1] in (" ", "\n", ".")
        ):
            return chunk[:i + 1] + "..."

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
        if clean in ("[성장과정]", "[지원동기]", "[직무 경험 및 강점]", "[입사 후 포부]"):
            label = clean[1:-1]
            content_map[label] = tokens[i + 1].strip() if i + 1 < len(tokens) else ""

    return [truncate_section(content_map.get(label, "")) for label in _SECTION_LABELS]


def build_resume_callback_response(sections: list[str]) -> dict:
    """4개 항목을 말풍선 2개로 묶은 카카오 콜백 응답 반환."""
    total = len(_SECTION_LABELS)
    bubble1 = "\n\n".join(
        f"📌 {i + 1}/{total} {_SECTION_LABELS[i]}\n{sections[i]}"
        for i in range(2)
    )
    bubble2 = "\n\n".join(
        f"📌 {i + 1}/{total} {_SECTION_LABELS[i]}\n{sections[i]}"
        for i in range(2, 4)
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
