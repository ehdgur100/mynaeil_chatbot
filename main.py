from fastapi import FastAPI, BackgroundTasks, Request
from onboarding import ResumeTask
import httpx
import onboarding
import resume

app = FastAPI(title="나의내일 챗봇 API")

_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [{"simpleText": {"text": "자기소개서 생성 중 오류가 발생했어요. 다시 시도해 주세요 😥"}}]
    },
}


async def _build_resume_response(task: ResumeTask) -> dict:
    """ResumeTask를 받아 자소서를 생성(또는 조회)하고 2-bubble 응답 반환."""
    if task.user_data is not None:
        resume_text = await resume.generate_resume(task.user_data)
        sections = resume.split_resume(resume_text)
        try:
            onboarding._save_resume(
                task.user_id,
                task.user_data.get("desired_job") or "",
                resume_text,
            )
        except Exception as e:
            print(f"[ResumeTask] DB 저장 실패: {e}")
    else:
        sections = task.sections or []

    return resume.build_resume_callback_response(sections)


async def send_resume_via_callback(task: ResumeTask, callback_url: str) -> None:
    print(f"[ResumeTask] 콜백 처리 시작 → {callback_url}")
    try:
        response_body = await _build_resume_response(task)
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=response_body, timeout=10.0)
            print(f"[ResumeTask] 콜백 전송 완료 (상태: {resp.status_code})")
    except Exception as e:
        print(f"[ResumeTask] 실패: {e}")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json=_ERROR_BODY, timeout=5.0)
        except:
            pass


@app.post("/api/chat")
async def chat_endpoint(request: Request, background_tasks: BackgroundTasks):
    raw = await request.json()
    user_request = raw.get("userRequest", {})
    user_message = user_request.get("utterance", "")
    user_id = user_request.get("user", {}).get("id", "unknown_user")
    callback_url = user_request.get("callbackUrl") or raw.get("callbackUrl")

    print(f"[알림] '{user_message}' | user: {user_id[:16]}...")

    result = await onboarding.handle_onboarding(user_id, user_message)

    if isinstance(result, ResumeTask):
        if callback_url:
            background_tasks.add_task(send_resume_via_callback, result, callback_url)
            return {
                "version": "2.0",
                "useCallback": True,
                "data": {"text": result.immediate_message},
            }
        # 콜백 URL 없음 (테스트 환경): 동기 처리
        try:
            return await _build_resume_response(result)
        except Exception as e:
            print(f"[ResumeTask] 동기 처리 실패: {e}")
            return _ERROR_BODY

    return result


@app.get("/")
def health_check():
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
