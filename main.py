from fastapi import FastAPI, BackgroundTasks, Request
from langchain_core.messages import HumanMessage
from graph import app_graph
import httpx

app = FastAPI(title="나의내일 챗봇 API")

_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [{"simpleText": {"text": "처리 도중 오류가 발생했어요. 다시 시도해 주세요 😥"}}]
    },
}


async def _run_graph_with_callback(user_id: str, user_message: str, callback_url: str) -> None:
    print(f"[Background] 그래프 실행 시작 (user: {user_id[:16]})")
    try:
        initial_state = {
            "messages": [HumanMessage(content=user_message)],
            "user_id": user_id,
            "intent": None,
            "kakao_response": None,
            "callback_url": callback_url,
        }
        final_state = await app_graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": user_id}},
        )
        kakao_resp = final_state.get("kakao_response") or _ERROR_BODY
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=kakao_resp, timeout=10.0)
            print(f"[Background] 콜백 전송 완료 (상태: {resp.status_code})")
    except Exception as e:
        print(f"[Background] 실패: {e}")
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

    if callback_url:
        background_tasks.add_task(_run_graph_with_callback, user_id, user_message, callback_url)
        return {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": "처리 중이에요. 잠시만 기다려주세요 ✍️"},
        }

    # callbackUrl 없는 경우 (테스트 환경): 동기 처리
    try:
        initial_state = {
            "messages": [HumanMessage(content=user_message)],
            "user_id": user_id,
            "intent": None,
            "kakao_response": None,
            "callback_url": None,
        }
        final_state = await app_graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": user_id}},
        )
        return final_state.get("kakao_response") or _ERROR_BODY
    except Exception as e:
        print(f"[chat_endpoint] 오류: {e}")
        return _ERROR_BODY


@app.get("/")
def health_check():
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
