from dataclasses import dataclass, field
from typing import Optional
from database.connection import supabase
from . import resume, guide
import database.operations as db_ops


@dataclass
class ResumeTask:
    user_id: str
    immediate_message: str
    user_data: Optional[dict] = None  # 생성 모드: OpenAI 호출 필요
    sections: Optional[list] = field(default=None)  # 조회 모드: 이미 분리된 항목


@dataclass
class ResumeRevisionTask:
    user_id: str
    immediate_message: str
    existing_content: str
    user_request: str
    revision_count: int
    desired_job: str = ""
    user_data: Optional[dict] = None


@dataclass
class ResumeReviewTask:
    user_id: str
    immediate_message: str
    resume_text: str
    desired_job: str = ""


@dataclass
class ApplyGuideTask:
    user_id: str
    job: dict


STEPS = [
    {
        "field": "career",
        "question": (
            "그동안 어떤 일을 가장 오래 하셨나요?\n"
            "구체적으로 말씀해 주실수록 더 좋은 자소서가 완성돼요 😊\n\n"
            "예) 자동차 부품 공장 생산직 15년, 하루 500개 부품 검수\n"
            "    식당 운영 10년, 직원 5명 관리 및 월 매출 3000만원\n"
            "    사무 행정 20년, 문서 관리 및 거래처 응대 담당"
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
        "quick_replies": [
            "생산·제조",
            "돌봄·요양",
            "청소·환경미화",
            "경비·시설관리",
            "배달·운전",
            "사무·행정",
            "기타",
        ],
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
        "quick_replies": [
            "주말 가능, 야간 가능",
            "주말 가능, 야간 불가",
            "주말 불가, 야간 불가",
            "시간 협의 가능",
        ],
    },
    {
        "field": "strengths",
        "question": (
            "주변에서 어떤 말을 자주 들으세요?\n"
            "또는 스스로 가장 자신 있는 점을 알려주세요 😊\n\n"
            "예) 꼼꼼하다, 책임감이 강하다, 손이 빠르다,\n"
            "    사람을 잘 챙긴다, 한번 맡은 일은 끝까지 한다"
        ),
        "quick_replies": [],
    },
    {
        "field": "goal",
        "question": (
            "지금 가장 중요한 것이 무엇인지 알려주세요.\n" "거의 다 왔어요 😊"
        ),
        "quick_replies": [
            "빠르게 취업해서 소득이 필요해요",
            "천천히 맞는 일을 찾고 싶어요",
            "일단 뭐든 해보고 싶어요",
        ],
    },
    {
        "field": "proud_experience",
        "question": (
            "일하면서 가장 뿌듯했던 순간이 있으셨나요?\n"
            "작은 일이라도 괜찮아요 😊\n\n"
            "예) 단골손님이 생겼을 때\n"
            "    어려운 문제를 내가 해결했을 때\n"
            "    후배나 동료를 도와줬을 때\n"
            "    힘든 상황에서도 끝까지 버텼을 때"
        ),
        "quick_replies": [],
    },
    {
        "field": "hardship",
        "question": (
            "일하면서 가장 힘들었던 상황과\n"
            "어떻게 극복하셨는지 알려주세요.\n"
            "자소서에서 가장 중요한 내용이 될 수 있어요 😊\n\n"
            "예) 갑자기 동료가 그만둬서 혼자 두 배 일을 했지만\n"
            "    끝까지 책임지고 마무리했어요."
        ),
        "quick_replies": [],
    },
]

_TEXT_STEPS = {0, 3, 5, 7, 8}  # 퀵리플라이 없이 텍스트로 입력받는 step
_retry_counts: dict[str, int] = {}  # key: f"{user_id}_{step}"

_DB_ERROR = {
    "version": "2.0",
    "template": {
        "outputs": [
            {"simpleText": {"text": "잠시 오류가 발생했어요. 다시 시도해 주세요 😥"}}
        ]
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
    result = supabase.table("users").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def _create_user(user_id: str) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users").insert({"user_id": user_id, "step": 0}).execute()


def _save_answer(user_id: str, field: str, answer: str, next_step: int) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users").update({field: answer, "step": next_step}).eq(
        "user_id", user_id
    ).execute()


def _reset_user(user_id: str) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users").upsert(
        {
            "user_id": user_id,
            "step": 0,
            "career": None,
            "skills": None,
            "desired_job": None,
            "location": None,
            "work_condition": None,
            "strengths": None,
            "goal": None,
            "proud_experience": None,
            "hardship": None,
            "resume_status": "none",
            "revision_count": 0,
        }
    ).execute()


def _save_resume(user_id: str, desired_job: str, content: str) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("resumes").delete().eq("user_id", user_id).execute()
    supabase.table("resumes").insert(
        {
            "user_id": user_id,
            "desired_job": desired_job,
            "content": content,
        }
    ).execute()


def _update_resume_status(user_id: str, status: str) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users").update({"resume_status": status}).eq(
        "user_id", user_id
    ).execute()


def _update_revision_count(user_id: str, new_count: int) -> None:
    if supabase is None:
        raise RuntimeError("Supabase 미연결")
    supabase.table("users").update({"revision_count": new_count}).eq(
        "user_id", user_id
    ).execute()


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
                return _build_response(
                    "아직 작성된 자소서가 없어요. 자소서를 먼저 작성해주세요 😊", []
                )
            return ResumeTask(
                user_id=user_id,
                immediate_message="저장된 자소서를 불러오고 있어요 📋",
                sections=resume.split_resume(saved["content"]),
            )

        user = _get_user(user_id)

        # resume_status 기반 상태 처리
        if user is not None and user.get("resume_status", "none") != "none":
            resume_status = user["resume_status"]

            if resume_status == "generated":
                if stripped == "네, 첨삭해주세요":
                    saved = _get_resume(user_id)
                    if saved is None:
                        return _build_response(
                            "저장된 자소서가 없어요. 먼저 자소서를 작성해주세요 😊", []
                        )
                    _update_resume_status(user_id, "reviewed")
                    return ResumeReviewTask(
                        user_id=user_id,
                        immediate_message="자소서를 첨삭 중이에요. 잠시만 기다려주세요 ✍️",
                        resume_text=saved["content"],
                        desired_job=saved.get("desired_job", ""),
                    )
                if stripped == "괜찮아요":
                    _update_resume_status(user_id, "editing")
                    return _build_response(
                        "수정하고 싶은 부분이 있으면 말씀해 주세요 😊\n"
                        "예) '지원동기를 더 구체적으로 써줘'\n"
                        "    '성장과정에 책임감 부분 강조해줘'\n"
                        "    '전체적으로 더 짧게 써줘'\n"
                        "만족하시면 아래 버튼을 눌러주세요.",
                        ["완료"],
                    )
                return _build_response(
                    "첨삭해드릴까요? 😊", ["네, 첨삭해주세요", "괜찮아요"]
                )

            if resume_status in ("reviewed", "editing"):
                if stripped == "완료":
                    _update_resume_status(user_id, "done")
                    return _build_response(
                        "자소서가 완성됐어요! 🎉\n"
                        "'자소서 보여줘'로 언제든 확인하세요 😊\n"
                        "이 공고에 어떻게 지원하는지 안내해드릴까요?",
                        ["네, 알려주세요", "괜찮아요"],
                    )
                saved = _get_resume(user_id)
                if saved is None:
                    return _build_response(
                        "저장된 자소서가 없어요. 먼저 자소서를 작성해주세요 😊", []
                    )
                revision_count = user.get("revision_count", 0)
                if revision_count >= 5:
                    return _build_response(
                        "수정은 최대 5번까지 가능해요.\n새로 작성하시려면 '처음부터'를 입력해 주세요 😊",
                        [],
                    )
                return ResumeRevisionTask(
                    user_id=user_id,
                    immediate_message="자소서를 수정 중이에요. 잠시만 기다려주세요 ✍️",
                    existing_content=saved["content"],
                    user_request=stripped,
                    revision_count=revision_count,
                    desired_job=saved.get("desired_job", ""),
                    user_data=dict(user),
                )

            if resume_status == "done":
                if stripped == "네, 알려주세요":
                    job_id = user.get("selected_job_id")
                    if not job_id:
                        return _build_response(
                            "지원할 공고 정보가 없어요.\n일자리 검색을 먼저 해주세요 😊", []
                        )
                    job = db_ops.get_job_by_id(str(job_id))
                    if not job:
                        return _build_response(
                            "공고 정보를 찾을 수 없어요 😥\n다시 시도해 주세요.", []
                        )
                    return ApplyGuideTask(user_id=user_id, job=job)
                if stripped == "괜찮아요":
                    return _build_response("필요하시면 언제든 말씀해 주세요 😊", [])
                return _build_response(
                    "자소서가 완성됐어요! 🎉\n'자소서 보여줘'로 언제든 확인하세요 😊",
                    [],
                )

        # 신규 사용자: DB에 없으면 생성 후 환영 메시지 + 첫 질문
        if user is None:
            _create_user(user_id)
            welcome = (
                "안녕하세요! 자기소개서 작성을 도와드릴게요 😊\n"
                "질문이 총 9개예요. 편하게 답변해 주세요!\n\n" + STEPS[0]["question"]
            )
            return _build_response(welcome, STEPS[0]["quick_replies"])

        step = user.get("step", 0)

        # 온보딩 완료 (step >= 9)
        if step >= 9:
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

        # 온보딩 진행 중 (step 0~8): 현재 step 답변 저장 → 다음 질문
        field = STEPS[step]["field"]

        if step in _TEXT_STEPS and len(stripped) <= 5:
            retry_key = f"{user_id}_{step}"
            count = _retry_counts.get(retry_key, 0)
            if count < 2:
                _retry_counts[retry_key] = count + 1
                return _build_response(
                    "조금 더 자세히 말씀해 주시겠어요? 😊\n예시를 참고해서 입력해 주세요.",
                    [],
                )
            _retry_counts.pop(retry_key, None)

        _save_answer(user_id, field, stripped, step + 1)

        if step + 1 >= 9:
            return ResumeTask(
                user_id=user_id,
                immediate_message="자소서를 작성 중이에요. 잠시만 기다려주세요 ✍️",
                user_data={**user, "hardship": stripped},
            )

        return _build_response(
            STEPS[step + 1]["question"], STEPS[step + 1]["quick_replies"]
        )

    except Exception as e:
        print(f"[Onboarding] 오류: {e}")
        return _DB_ERROR


async def resume_gen(state: dict) -> dict:
    user_id = state["user_id"]
    user_message = state["messages"][-1].content

    result = await handle_onboarding(user_id, user_message)

    if isinstance(result, ResumeTask):
        if result.user_data is not None:
            try:
                resume_text = await resume.generate_resume(result.user_data)
                sections = resume.split_resume(resume_text)
                _save_resume(result.user_id, result.user_data.get("desired_job") or "", resume_text)
                _update_resume_status(result.user_id, "generated")
                kakao_response = resume.build_resume_callback_response(sections)
                kakao_response["template"]["outputs"].append({"simpleText": {"text": "첨삭해드릴까요? 😊"}})
                kakao_response["template"]["quickReplies"] = [
                    {"action": "message", "label": "네, 첨삭해주세요", "messageText": "네, 첨삭해주세요"},
                    {"action": "message", "label": "괜찮아요", "messageText": "괜찮아요"},
                ]
            except Exception as e:
                print(f"[resume_gen] 자소서 생성 오류: {e}")
                kakao_response = _DB_ERROR
        else:
            sections = result.sections or []
            kakao_response = resume.build_resume_callback_response(sections)

    elif isinstance(result, ResumeReviewTask):
        try:
            reviewed_text = await resume.rag_review(result.user_id, result.resume_text)
            sections = resume.split_resume(reviewed_text)
            _save_resume(result.user_id, result.desired_job, reviewed_text)
            completion_msg = (
                "첨삭이 완료됐어요 😊\n"
                "수정하고 싶은 부분이 있으면 말씀해 주세요.\n"
                "만족하시면 아래 버튼을 눌러주세요."
            )
            kakao_response = resume.build_resume_callback_response(sections)
            kakao_response["template"]["outputs"].append({"simpleText": {"text": completion_msg}})
            kakao_response["template"]["quickReplies"] = [
                {"action": "message", "label": "완료", "messageText": "완료"},
            ]
        except Exception as e:
            print(f"[resume_gen] 첨삭 오류: {e}")
            kakao_response = _DB_ERROR

    elif isinstance(result, ResumeRevisionTask):
        try:
            revised_text = await resume.revise_resume(
                result.existing_content, result.user_request, result.user_data or {}
            )
            sections = resume.split_resume(revised_text)
            new_count = result.revision_count + 1
            _save_resume(result.user_id, result.desired_job, revised_text)
            _update_revision_count(result.user_id, new_count)
            remaining = 5 - new_count
            if remaining > 0:
                completion_msg = (
                    f"수정이 완료됐어요 😊\n"
                    f"남은 수정 횟수: {remaining}번\n"
                    f"더 수정하시거나 만족하시면 완료 버튼을 눌러주세요."
                )
            else:
                completion_msg = (
                    "수정이 완료됐어요 😊\n"
                    "수정 횟수를 모두 사용했어요.\n"
                    "만족하시면 완료 버튼을 눌러주세요."
                )
            kakao_response = resume.build_resume_callback_response(sections)
            kakao_response["template"]["outputs"].append({"simpleText": {"text": completion_msg}})
            kakao_response["template"]["quickReplies"] = [
                {"action": "message", "label": "완료", "messageText": "완료"},
            ]
        except Exception as e:
            print(f"[resume_gen] 수정 오류: {e}")
            kakao_response = _DB_ERROR

    elif isinstance(result, ApplyGuideTask):
        try:
            guide_text = await guide.get_apply_guide(result.job)
            kakao_response = _build_response(guide_text, [])
        except Exception as e:
            print(f"[resume_gen] 지원 안내 오류: {e}")
            kakao_response = _build_response(
                "지원 방법 안내 중 오류가 발생했어요 😥\n다시 시도해 주세요.", []
            )

    else:
        kakao_response = result

    return {"kakao_response": kakao_response}
