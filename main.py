import re
import sys

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
from langchain_core.messages import HumanMessage

from graph import app_graph
from nodes.navigation import add_navigation_buttons
import database.operations as db_ops


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
    input_clean = user_message.strip().lower()

    # 자소서 검증/첨삭/수정/피드백 키워드
    if any(k in input_clean for k in ["검증", "평가", "첨삭", "피드백", "판별", "수정", "고쳐"]):
        return True

    # 교육 신청 가이드 키워드
    if any(
        k in input_clean
        for k in ["신청 가이드", "준비 가이드", "신청 준비", "교육 신청", "어떻게 신청"]
    ) or re.search(r"\d+번\s*(교육|과정)?\s*(신청|가이드|준비)", input_clean):
        return True

    # DB 기반 상태 체크 (step 5 벡터 검색 / step 8 자소서 생성 / editing·done 수정)
    try:
        profile = db_ops.get_user_profile(user_id)
        if profile:
            step = profile.get("step", 0)
            resume_status = profile.get("resume_status")
            reset_keywords = ["처음부터", "초기화", "다시 시작"]

            if step == 5 and not any(k in input_clean for k in reset_keywords):
                return True

            if step == 8 and not any(k in input_clean for k in reset_keywords):
                return True

            if resume_status in ("editing", "done"):
                if not any(k in input_clean for k in ["완료", "처음부터", "초기화"]):
                    return True
    except Exception as e:
        print(f"[is_slow_request check error] {e}")

    return False


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
        kakao_resp = add_navigation_buttons(final_state.get("kakao_response") or _ERROR_BODY)
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
        return add_navigation_buttons(final_state.get("kakao_response") or _ERROR_BODY)
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
