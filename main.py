from fastapi import FastAPI, BackgroundTasks, Request
from typing import Any, Dict, Optional
from langchain_core.messages import HumanMessage
from graph import app_graph
import httpx

app = FastAPI(title="나의내일 챗봇 API (Callback 지원)")


async def send_callback_response(callback_url: str, initial_state: Dict[str, Any], config: Dict[str, Any]):
    """백그라운드에서 LangGraph를 실행하고 결과를 카카오 콜백 URL로 전송합니다."""
    print(f"[Callback] 처리 시작 → {callback_url}")
    try:
        final_state = await app_graph.ainvoke(initial_state, config=config)
        ai_response = final_state["messages"][-1].content

        callback_body = {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": ai_response}}]
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=callback_body, timeout=10.0)
            print(f"[Callback] 전송 완료 (상태: {resp.status_code})")

    except Exception as e:
        print(f"[Callback] 에러: {e}")
        try:
            error_body = {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": "죄송합니다. 잠시 후 다시 시도해 주세요."}}]}
            }
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json=error_body, timeout=5.0)
        except:
            pass


@app.post("/api/chat")
async def chat_endpoint(request: Request, background_tasks: BackgroundTasks):
    raw = await request.json()

    user_request = raw.get("userRequest", {})
    user_message = user_request.get("utterance", "")
    user_id = user_request.get("user", {}).get("id", "unknown_user")

    # callbackUrl 탐색 (userRequest 안 또는 root level)
    callback_url = user_request.get("callbackUrl") or raw.get("callbackUrl")

    action_data = raw.get("action", {})
    client_extra = action_data.get("clientExtra", {})
    explicit_intent = client_extra.get("intent", None)

    print(f"[알림] '{user_message}' | 콜백: {bool(callback_url)} | user: {user_id[:16]}...")

    initial_state = {
        "user_id": user_id,
        "messages": [HumanMessage(content=user_message)],
        "intent": explicit_intent
    }
    config = {"configurable": {"thread_id": user_id}}

    # ── 경우 1: callbackUrl이 있음 (카카오 콜백 정상 작동 시) ──
    # 카카오가 첫 요청부터 callbackUrl을 보내주면 비동기로 처리합니다.
    if callback_url:
        print(f"[Callback] 비동기 처리 시작 (URL: {callback_url[:40]}...)")
        background_tasks.add_task(send_callback_response, callback_url, initial_state, config)
        return {
            "version": "2.0",
            "useCallback": True,
            "data": {
                "text": "잠시만 기다려 주세요. 답변을 준비 중입니다..."
            }
        }

    # ── 경우 2: callbackUrl이 없음 (설정 미적용 또는 봇 테스트 창) ──
    # 카카오가 callbackUrl을 보내지 않았으므로 무조건 5초 안에 
    # 일반 응답(동기 방식)으로 답변을 줘야 합니다.
    print(f"[알림] 콜백 URL 없음 → 동기 처리 시작")
    final_state = await app_graph.ainvoke(initial_state, config=config)
    ai_response = final_state["messages"][-1].content
    
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": ai_response}}]}
    }


@app.get("/")
def health_check():
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
