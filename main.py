import re
import sys

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
from langchain_core.messages import HumanMessage

from graph import app_graph


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


app = FastAPI(title="나의내일 챗봇 API")

_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [
            {
                "simpleText": {
                    "text": "처리 중 오류가 발생했어요. 다시 시도해 주세요."
                }
            }
        ]
    },
}


def is_slow_request(user_id: str, user_message: str) -> bool:
    message_clean = user_message.strip().lower()
    slow_keywords = [
        "검증",
        "평가",
        "첨삭",
        "피드백",
        "자소서 수정",
        "교육 신청 가이드",
        "신청 준비",
    ]
    numbered_edu_guide = re.search(
        r"\d+\s*번\s*(교육|과정)?\s*(신청|가이드|준비)", message_clean
    )
    return any(keyword in message_clean for keyword in slow_keywords) or bool(
        numbered_edu_guide
    )


async def _run_graph_with_callback(
    user_id: str, user_message: str, callback_url: str
) -> None:
    print(f"[Background] graph start user={user_id[:16]}")
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
            print(f"[Background] callback sent status={resp.status_code}")
    except Exception as exc:
        print(f"[Background] failed: {exc}")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json=_ERROR_BODY, timeout=5.0)
        except Exception:
            pass


@app.post("/api/chat")
async def chat_endpoint(request: Request, background_tasks: BackgroundTasks):
    raw = await request.json()
    user_request = raw.get("userRequest", {})
    user_message = user_request.get("utterance", "")
    user_id = user_request.get("user", {}).get("id", "unknown_user")
    callback_url = user_request.get("callbackUrl") or raw.get("callbackUrl")

    try:
        print(f"[chat] '{user_message}' | user={user_id[:16]}...")
    except Exception:
        pass

    if callback_url and is_slow_request(user_id, user_message):
        background_tasks.add_task(
            _run_graph_with_callback, user_id, user_message, callback_url
        )
        return {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": "처리 중이에요. 잠시만 기다려 주세요."},
        }

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
    except Exception as exc:
        print(f"[chat_endpoint] error: {exc}")
        return _ERROR_BODY


@app.post("/api/recommend")
async def recommend_endpoint(request: Request):
    try:
        raw = await request.json()
        user_request = raw.get("userRequest", {})
        user_id = user_request.get("user", {}).get("id", "unknown_user")

        print(f"[recommend] user_id={user_id}")
        from data_pipeline import recommend

        jobs = await recommend.recommend_jobs_for_user(user_id, limit=5)
        return recommend.build_kakao_carousel_response(jobs)
    except Exception as exc:
        print(f"[recommend] error: {exc}")
        return _ERROR_BODY


@app.get("/")
def health_check():
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
