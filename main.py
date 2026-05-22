from fastapi import FastAPI, BackgroundTasks, Request
from onboarding import ResumeTask, ResumeRevisionTask, ResumeReviewTask
import httpx
import asyncio

app = FastAPI(title="나의내일 챗봇 API")

# 카카오톡 서버나 챗봇 로직 내부에서 오류 발생 시 유저에게 반환할 기본 안내 템플릿입니다.
_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [
            {
                "simpleText": {
                    "text": "처리 도중 오류가 발생했어요. 다시 시도해 주세요 😥"
                }
            }
        ]
    },
}

_REVISION_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [
            {"simpleText": {"text": "수정 중 오류가 발생했어요. 다시 시도해 주세요 😥"}}
        ]
    },
}

_REVIEW_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [
            {"simpleText": {"text": "첨삭 중 오류가 발생했어요. 다시 시도해 주세요 😥"}}
        ]
    },
}


async def _build_resume_response(task: ResumeTask) -> dict:
    """ResumeTask를 받아 자소서를 생성(또는 조회)하고 응답 반환."""
    if task.user_data is not None:
        resume_text = await resume.generate_resume(task.user_data)
        sections = resume.split_resume(resume_text)
        try:
            onboarding._save_resume(
                task.user_id,
                task.user_data.get("desired_job") or "",
                resume_text,
            )
            onboarding._update_resume_status(task.user_id, "generated")
        except Exception as e:
            print(f"[ResumeTask] DB 저장 실패: {e}")
        response = resume.build_resume_callback_response(sections)
        response["template"]["outputs"].append(
            {"simpleText": {"text": "첨삭해드릴까요? 😊"}}
        )
        response["template"]["quickReplies"] = [
            {
                "action": "message",
                "label": "네, 첨삭해주세요",
                "messageText": "네, 첨삭해주세요",
            },
            {"action": "message", "label": "괜찮아요", "messageText": "괜찮아요"},
        ]
    else:
        sections = task.sections or []
        response = resume.build_resume_callback_response(sections)
    return response


async def _build_review_response(task: ResumeReviewTask) -> dict:
    """ResumeReviewTask를 받아 RAG 첨삭 후 3-bubble 응답 반환."""
    reviewed_text = await resume.rag_review(task.user_id, task.resume_text)
    sections = resume.split_resume(reviewed_text)
    try:
        onboarding._save_resume(task.user_id, task.desired_job, reviewed_text)
    except Exception as e:
        print(f"[ReviewTask] DB 저장 실패: {e}")

    completion_msg = (
        "첨삭이 완료됐어요 😊\n"
        "수정하고 싶은 부분이 있으면 말씀해 주세요.\n"
        "만족하시면 아래 버튼을 눌러주세요."
    )
    response = resume.build_resume_callback_response(sections)
    response["template"]["outputs"].append({"simpleText": {"text": completion_msg}})
    response["template"]["quickReplies"] = [
        {"action": "message", "label": "완료", "messageText": "완료"},
    ]
    return response


async def _build_revision_response(task: ResumeRevisionTask) -> dict:
    """ResumeRevisionTask를 받아 자소서를 수정하고 3-bubble 응답 반환."""
    revised_text = await resume.revise_resume(
        task.existing_content, task.user_request, task.user_data or {}
    )
    sections = resume.split_resume(revised_text)
    new_count = task.revision_count + 1
    try:
        onboarding._save_resume(task.user_id, task.desired_job, revised_text)
        onboarding._update_revision_count(task.user_id, new_count)
    except Exception as e:
        print(f"[RevisionTask] DB 저장 실패: {e}")

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
    response = resume.build_resume_callback_response(sections)
    response["template"]["outputs"].append({"simpleText": {"text": completion_msg}})
    response["template"]["quickReplies"] = [
        {"action": "message", "label": "완료", "messageText": "완료"},
    ]
    return response


async def send_review_via_callback(task: ResumeReviewTask, callback_url: str) -> None:
    print(f"[ReviewTask] 콜백 처리 시작 → {callback_url}")
    try:
        response_body = await _build_review_response(task)
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=response_body, timeout=10.0)
            print(f"[ReviewTask] 콜백 전송 완료 (상태: {resp.status_code})")
    except Exception as e:
        print(f"[ReviewTask] 실패: {e}")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json=_REVIEW_ERROR_BODY, timeout=5.0)
        except:
            pass


async def send_resume_via_callback(task: ResumeTask, callback_url: str) -> None:
    print(f"[ResumeTask] 콜백 처리 시작 → {callback_url}")
    try:
        profile = db_ops.get_user_profile(user_id)
        if profile:
            step = profile.get("step", 0)
            # 마지막 단계(6단계)에서 답변을 등록하는 중
            if step == 6 and input_clean != "처음부터":
                return True, "자기소개서를 작성 중이에요. 잠시만 기다려주세요 ✍️"
            # 온보딩 완료 상태에서 이전 정보로 자소서 다시 만들기 요청
            if step >= 7 and input_clean == "이전 정보로 자소서 작성하기":
                return True, "자기소개서를 작성 중이에요. 잠시만 기다려주세요 ✍️"
    except Exception as e:
        print(f"[is_slow_request Warning] 유저 프로필 조회 실패: {e}")

    return False, ""


async def run_graph_in_background(user_id: str, user_message: str, callback_url: str):
    """
    [백그라운드 비동기 처리기]
    카카오톡 5초 타임아웃을 피하기 위해, 백그라운드 스레드에서 랭그래프를 돌려
    답변을 완성한 후 카카오톡 콜백 서버 주소로 전송합니다.
    """
    print(
        f"[Background] 랭그래프 비동기 처리 시작 (User: {user_id[:16]}, Callback: {callback_url})"
    )

    config_dict = {"configurable": {"thread_id": user_id}}

    # 이전 대화 턴의 의도(intent)와 응답(kakao_response)이 현재 턴에 영향을 주지 않도록 초기화해 줍니다.
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "intent": None,
        "kakao_response": None,
        "callback_url": callback_url,
    }

    try:
        # LangGraph 워크플로우 실행
        final_state = await app_graph.ainvoke(initial_state, config=config_dict)
        kakao_resp = final_state.get("kakao_response")

        # 챗봇 방에서 리치 템플릿(kakao_response)을 만들어내지 못한 경우, 텍스트 메시지를 기본값으로 감싸줍니다.
        if not kakao_resp:
            last_msg = (
                final_state["messages"][-1].content
                if final_state.get("messages")
                else "처리가 완료되었습니다."
            )
            kakao_resp = {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": last_msg}}]},
            }

        # HTTP 통신을 사용해 카카오 콜백 서버 주소로 최종 답변 JSON을 보냅니다.
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=kakao_resp, timeout=10.0)
            print(f"[Background] 콜백 전송 성공 (상태코드: {resp.status_code})")
    except Exception as e:
        print(f"[Background Error] 비동기 그래프 처리 중 예외 발생: {e}")
        try:
            # 오류 발생 시 사용자에게 에러 안내 콜백 발송
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json=_ERROR_BODY, timeout=5.0)
        except:
            pass


async def send_revision_via_callback(
    task: ResumeRevisionTask, callback_url: str
) -> None:
    print(f"[RevisionTask] 콜백 처리 시작 → {callback_url}")
    try:
        response_body = await _build_revision_response(task)
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=response_body, timeout=10.0)
            print(f"[RevisionTask] 콜백 전송 완료 (상태: {resp.status_code})")
    except Exception as e:
        print(f"[RevisionTask] 실패: {e}")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json=_REVISION_ERROR_BODY, timeout=5.0)
        except:
            pass


@app.post("/api/chat")
async def chat_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    [카카오톡 챗봇 연동 메인 API]
    카카오톡 i 오픈빌더에서 유저 발화가 들어오는 단일 통로입니다.
    """
    raw = await request.json()
    user_request = raw.get("userRequest", {})
    user_message = user_request.get("utterance", "")
    user_id = user_request.get("user", {}).get("id", "unknown_user")
    callback_url = user_request.get("callbackUrl") or raw.get("callbackUrl")

    print(f"[알림] '{user_message}' | user: {user_id[:16]}...")

    # 1. 5초 초과 위험 작업 및 콜백 URL 존재 시 비동기 처리로 우회
    slow, wait_msg = is_slow_request(user_id, user_message)
    if slow and callback_url:
        # 백그라운드로 랭그래프 작업을 넘겨 5초 제약을 회피하고,
        # 사용자에게는 즉시 "대기 안내 문구"를 전달하여 응답 지연을 방지합니다.
        background_tasks.add_task(
            run_graph_in_background, user_id, user_message, callback_url
        )
        return {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": wait_msg},
        }

    if isinstance(result, ResumeReviewTask):
        if callback_url:
            background_tasks.add_task(send_review_via_callback, result, callback_url)
            return {
                "version": "2.0",
                "useCallback": True,
                "data": {"text": result.immediate_message},
            }
        try:
            return await _build_review_response(result)
        except Exception as e:
            print(f"[ReviewTask] 동기 처리 실패: {e}")
            return _REVIEW_ERROR_BODY

    if isinstance(result, ResumeRevisionTask):
        if callback_url:
            background_tasks.add_task(send_revision_via_callback, result, callback_url)
            return {
                "version": "2.0",
                "useCallback": True,
                "data": {"text": result.immediate_message},
            }
        try:
            return await _build_revision_response(result)
        except Exception as e:
            print(f"[RevisionTask] 동기 처리 실패: {e}")
            return _REVISION_ERROR_BODY

    if isinstance(result, ResumeTask):
        if callback_url:
            background_tasks.add_task(send_resume_via_callback, result, callback_url)
            return {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": last_msg}}]},
            }
        try:
            return await _build_resume_response(result)
        except Exception as e:
            print(f"[ResumeTask] 동기 처리 실패: {e}")
            return _ERROR_BODY

    return result


@app.get("/")
def health_check():
    """챗봇 서버 상태 모니터링용 엔드포인트"""
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
