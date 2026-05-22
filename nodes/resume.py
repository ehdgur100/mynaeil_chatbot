import re
from typing import Dict, Any, Optional
from state import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_smart, get_content
import database.operations as db_ops

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

STEPS = [
    {
        "field": "career",
        "question": (
            "그동안 어떤 일을 가장 오래 하셨나요?\n"
            "직장이나 자영업, 아르바이트 모두 괜찮아요 😊\n"
            "(예: 식당 운영 10년, 공장 생산직 15년, 사무 행정 20년)"
        ),
        "quick_replies": [],
    },
    {
        "field": "skills",
        "question": (
            "현재 갖고 계신 자격증이나 면허가 있으신가요?\n"
            "운전면허, 지게차, 요양보호사, 조리사 등 어떤 것이든 좋아요.\n"
            "없으시면 아래 버튼을 눌러주세요 😊"
        ),
        "quick_replies": ["없음"],
    },
    {
        "field": "desired_job",
        "question": (
            "앞으로 어떤 종류의 일을 해보고 싶으신가요?\n"
            "아래 중 선택하시거나 직접 입력해 주세요 😊"
        ),
        "quick_replies": ["생산·제조", "돌봄·요양", "청소·환경미화", "경비·시설관리", "배달·운전", "사무·행정", "기타"],
    },
    {
        "field": "location",
        "question": (
            "주로 어느 지역에서 일하고 싶으신가요?\n"
            "(예: 서울 강서구, 경기 수원시, 집에서 30분 이내)"
        ),
        "quick_replies": [],
    },
    {
        "field": "work_condition",
        "question": (
            "근무 관련해서 가능하신 조건을 알려주세요.\n"
            "아래 버튼으로 선택하시거나 직접 입력하셔도 됩니다 😊\n"
            "(예: 주말 가능, 야간 불가, 하루 6시간 이내)"
        ),
        "quick_replies": ["주말 가능, 야간 가능", "주말 가능, 야간 불가", "주말 불가, 야간 불가", "시간 협의 가능"],
    },
    {
        "field": "strengths",
        "question": (
            "주변에서 어떤 말을 자주 들으세요?\n"
            "또는 스스로 가장 자신 있는 점을 알려주세요 😊\n"
            "(예: 꼼꼼하다, 책임감이 강하다, 손이 빠르다, 사람을 잘 챙긴다)"
        ),
        "quick_replies": [],
    },
    {
        "field": "goal",
        "question": (
            "마지막 질문이에요! 거의 다 왔어요 😊\n"
            "지금 가장 중요한 것이 무엇인지 알려주세요."
        ),
        "quick_replies": ["빠르게 취업해서 소득이 필요해요", "천천히 맞는 일을 찾고 싶어요", "일단 뭐든 해보고 싶어요"],
    },
]

def _build_response(text: str, quick_replies: list) -> dict:
    resp = {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }
    if quick_replies:
        resp["template"]["quickReplies"] = [
            {"action": "message", "label": lb, "messageText": lb}
            for lb in quick_replies
        ]
    return resp

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
            ],
            "quickReplies": [
                {"action": "message", "label": "🔍 자소서 검증하기", "messageText": "자소서 검증해줘"},
                {"action": "message", "label": "✍️ 새로 작성하기", "messageText": "처음부터"},
                {"action": "message", "label": "💼 일자리 검색하기", "messageText": "일자리 추천해줘"}
            ]
        },
    }

async def generate_resume_text(user_data: dict) -> str:
    user_prompt = _USER_TEMPLATE.format(
        career=user_data.get("career") or "",
        skills=user_data.get("skills") or "",
        desired_job=user_data.get("desired_job") or "",
        location=user_data.get("location") or "",
        work_condition=user_data.get("work_condition") or "",
        strengths=user_data.get("strengths") or "",
        goal=user_data.get("goal") or "",
    )
    response = await llm_smart.ainvoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    return get_content(response)

async def resume_gen(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 B 담당] 자소서 생성을 위한 온보딩 질문 수집 및 최종 자소서 생성 노드
    """
    print("[Node] resume_gen 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""
    stripped = user_input.strip()

    # 1. "처음부터" 강제 초기화 처리
    if stripped == "처음부터":
        db_ops.reset_user_profile(user_id)
        msg = "처음부터 다시 시작할게요! 😊\n\n" + STEPS[0]["question"]
        kakao_resp = _build_response(msg, STEPS[0]["quick_replies"])
        return {
            "messages": [AIMessage(content=msg)],
            "kakao_response": kakao_resp,
            "intent": "resume_gen"
        }

    # 2. "자소서 보여줘" 또는 "저장된 자소서" 처리
    if stripped in ("자소서 보여줘", "저장된 자소서"):
        saved = db_ops.get_resume(user_id)
        if saved is None:
            msg = "아직 작성된 자소서가 없어요. 자소서를 먼저 작성해주세요 😊"
            return {
                "messages": [AIMessage(content=msg)],
                "kakao_response": _build_response(msg, []),
                "intent": "resume_gen"
            }
        sections = split_resume(saved["content"])
        kakao_resp = build_resume_callback_response(sections)
        return {
            "messages": [AIMessage(content="저장된 자소서를 불러왔습니다.")],
            "kakao_response": kakao_resp,
            "intent": "resume_gen"
        }

    # 3. 유저 프로필 조회
    profile = db_ops.get_user_profile(user_id)

    # 신규 사용자: DB에 등록 후 첫 번째 질문 출력
    if profile is None:
        db_ops.create_user_profile(user_id)
        welcome = (
            "안녕하세요! 자기소개서 작성을 도와드릴게요 😊\n"
            "질문이 총 7개예요. 편하게 답변해 주세요!\n\n"
            + STEPS[0]["question"]
        )
        kakao_resp = _build_response(welcome, STEPS[0]["quick_replies"])
        return {
            "messages": [AIMessage(content=welcome)],
            "kakao_response": kakao_resp,
            "intent": "resume_gen"
        }

    step = profile.get("step", 0)

    # 4. 온보딩 완료 상태 (step >= 7) 처리
    if step >= 7:
        if stripped == "새로 작성하기":
            db_ops.reset_user_profile(user_id)
            msg = "새로 시작할게요! 😊\n\n" + STEPS[0]["question"]
            kakao_resp = _build_response(msg, STEPS[0]["quick_replies"])
            return {
                "messages": [AIMessage(content=msg)],
                "kakao_response": kakao_resp,
                "intent": "resume_gen"
            }
        elif stripped == "이전 정보로 자소서 작성하기":
            # 이전 프로필로 자소서 재발행
            resume_text = await generate_resume_text(profile)
            db_ops.save_resume(user_id, profile.get("desired_job") or "", resume_text)
            sections = split_resume(resume_text)
            kakao_resp = build_resume_callback_response(sections)
            return {
                "messages": [AIMessage(content="이전 정보로 자소서를 다시 생성했습니다.")],
                "kakao_response": kakao_resp,
                "intent": "resume_gen"
            }
        else:
            msg = "이전에 입력하신 정보가 있어요. 어떻게 할까요?"
            kakao_resp = _build_response(msg, ["새로 작성하기", "이전 정보로 자소서 작성하기"])
            return {
                "messages": [AIMessage(content=msg)],
                "kakao_response": kakao_resp,
                "intent": "resume_gen"
            }

    # 5. 온보딩 진행 중 (step 0 ~ 6) 답변 저장 및 분기 처리
    field = STEPS[step]["field"]
    next_step = step + 1
    db_ops.save_onboarding_answer(user_id, field, stripped, next_step)

    # 마지막 단계 완료 시 자소서 생성 수행
    if next_step >= 7:
        user_data = {**profile, field: stripped}
        resume_text = await generate_resume_text(user_data)
        db_ops.save_resume(user_id, user_data.get("desired_job") or "", resume_text)
        sections = split_resume(resume_text)
        kakao_resp = build_resume_callback_response(sections)
        return {
            "messages": [AIMessage(content="자소서를 성공적으로 완성했습니다.")],
            "kakao_response": kakao_resp,
            "intent": "resume_gen"
        }

    # 다음 질문으로 유도
    next_question = STEPS[next_step]["question"]
    next_replies = STEPS[next_step]["quick_replies"]
    kakao_resp = _build_response(next_question, next_replies)
    return {
        "messages": [AIMessage(content=next_question)],
        "kakao_response": kakao_resp,
        "intent": "resume_gen"
    }
