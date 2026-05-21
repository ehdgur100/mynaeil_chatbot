from dataclasses import dataclass, field
from typing import Optional
from database import supabase
import resume


@dataclass
class ResumeTask:
    user_id: str
    immediate_message: str
    user_data: Optional[dict] = None   # 생성 모드: OpenAI 호출 필요
    sections: Optional[list] = field(default=None)  # 조회 모드: 이미 분리된 항목

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

_DB_ERROR = {
    "version": "2.0",
    "template": {
        "outputs": [{"simpleText": {"text": "잠시 오류가 발생했어요. 다시 시도해 주세요 😥"}}]
    },
}


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


def _get_user(user_id: str) -> Optional[dict]:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    result = supabase.table("users2").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def _create_user(user_id: str) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users2").insert({"user_id": user_id, "step": 0}).execute()


def _save_answer(user_id: str, field: str, answer: str, next_step: int) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users2").update(
        {field: answer, "step": next_step}
    ).eq("user_id", user_id).execute()


def _reset_user(user_id: str) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users2").upsert({
        "user_id": user_id, "step": 0,
        "career": None, "skills": None, "desired_job": None,
        "location": None, "work_condition": None,
        "strengths": None, "goal": None,
    }).execute()


def _save_resume(user_id: str, desired_job: str, content: str) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("resumes").delete().eq("user_id", user_id).execute()
    supabase.table("resumes").insert({
        "user_id": user_id,
        "desired_job": desired_job,
        "content": content,
    }).execute()


def _get_resume(user_id: str) -> Optional[dict]:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    result = supabase.table("resumes").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


async def handle_onboarding(user_id: str, user_input: str) -> dict:
    try:
        stripped = user_input.strip()

        # "처음부터" 입력 시 언제든 초기화
        if stripped == "처음부터":
            _reset_user(user_id)
            msg = "처음부터 다시 시작할게요! 😊\n\n" + STEPS[0]["question"]
            return _build_response(msg, STEPS[0]["quick_replies"])

        # 저장된 자소서 조회
        if stripped in ("자소서 보여줘", "저장된 자소서"):
            saved = _get_resume(user_id)
            if saved is None:
                return _build_response("아직 작성된 자소서가 없어요. 자소서를 먼저 작성해주세요 😊", [])
            return ResumeTask(
                user_id=user_id,
                immediate_message="저장된 자소서를 불러오고 있어요 📋",
                sections=resume.split_resume(saved["content"]),
            )

        user = _get_user(user_id)

        # 신규 사용자: DB에 없으면 생성 후 환영 메시지 + 첫 질문
        if user is None:
            _create_user(user_id)
            welcome = (
                "안녕하세요! 자기소개서 작성을 도와드릴게요 😊\n"
                "질문이 총 7개예요. 편하게 답변해 주세요!\n\n"
                + STEPS[0]["question"]
            )
            return _build_response(welcome, STEPS[0]["quick_replies"])

        step = user.get("step", 0)

        # 온보딩 완료 (step >= 7)
        if step >= 7:
            if stripped == "새로 작성하기":
                _reset_user(user_id)
                msg = "새로 시작할게요! 😊\n\n" + STEPS[0]["question"]
                return _build_response(msg, STEPS[0]["quick_replies"])
            if stripped == "이전 정보로 자소서 작성하기":
                return ResumeTask(
                    user_id=user_id,
                    immediate_message="자소서를 작성 중이에요. 잠시만 기다려주세요 ✍️",
                    user_data=dict(user),
                )
            # 그 외 입력 → 재방문 안내
            return _build_response(
                "이전에 입력하신 정보가 있어요. 어떻게 할까요?",
                ["새로 작성하기", "이전 정보로 자소서 작성하기"],
            )

        # 온보딩 진행 중 (step 0~6): 현재 step 답변 저장 → 다음 질문
        field = STEPS[step]["field"]
        _save_answer(user_id, field, stripped, step + 1)

        if step + 1 >= 7:
            return ResumeTask(
                user_id=user_id,
                immediate_message="자소서를 작성 중이에요. 잠시만 기다려주세요 ✍️",
                user_data={**user, "goal": stripped},
            )

        return _build_response(STEPS[step + 1]["question"], STEPS[step + 1]["quick_replies"])

    except Exception as e:
        print(f"[Onboarding] 오류: {e}")
        return _DB_ERROR
