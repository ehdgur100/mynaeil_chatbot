from fastapi import FastAPI, BackgroundTasks, Request
from langchain_core.messages import HumanMessage
from graph import app_graph
import httpx
import database.operations as db_ops

app = FastAPI(title="나의내일 챗봇 API")

_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [{"simpleText": {"text": "처리 도중 오류가 발생했어요. 다시 시도해 주세요 😥"}}]
    },
}


def is_slow_request(user_id: str, user_message: str) -> bool:
    """오래 걸리는 요청(자소서 생성/첨삭/수정 등)인지 판단합니다."""
    message_clean = user_message.strip().lower()
    
    # 1. 명시적인 자소서 검증/첨삭/수정/피드백 키워드가 존재하면 느린 요청으로 취급
    if any(k in message_clean for k in ["검증", "평가", "첨삭", "피드백", "판별", "수정", "고쳐"]):
        return True
        
    # 2. 사용자 DB 상태 확인
    try:
        profile = db_ops.get_user_profile(user_id)
        if profile:
            step = profile.get("step", 0)
            resume_status = profile.get("resume_status")
            
            # 자소서 온보딩 9단계(마지막 단계 step == 8) 완료 응답인 경우 (단, 처음부터 등 초기화 키워드 제외)
            if step == 8 and not any(k in message_clean for k in ["처음부터", "초기화", "다시 시작"]):
                return True
                
            # 자소서 수정 모드(editing)이거나 완료된 후(done) 사용자가 자소서 수정을 직접 타이핑하는 경우
            if resume_status in ("editing", "done"):
                # 완료, 처음부터 등의 퀵 버튼은 동기(빠른) 처리 대상
                if not any(k in message_clean for k in ["완료", "처음부터", "초기화"]):
                    return True
    except Exception as e:
        print(f"[is_slow_request check error] {e}")
        
    return False


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

    slow = is_slow_request(user_id, user_message)
    if callback_url and slow:
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


@app.post("/api/recommend")
async def recommend_endpoint(request: Request):
    try:
        raw = await request.json()
        user_request = raw.get("userRequest", {})
        user_id = user_request.get("user", {}).get("id", "unknown_user")
        
        print(f"[추천 API 호출] user_id: {user_id}")
        
        # recommend.py의 함수들을 호출하여 추천 공고를 가져오고 캐러셀로 변환합니다.
        from data_pipeline import recommend
        
        # 유저 ID를 기반으로 추천 공고 Top 5 가져오기
        jobs = await recommend.recommend_jobs_for_user(user_id, limit=5)
        
        # 카카오톡 캐러셀 JSON 포맷으로 변환 후 응답
        return recommend.build_kakao_carousel_response(jobs)
        
    except Exception as e:
        print(f"[추천 API 에러] {e}")
        return {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": "추천 공고를 불러오는 중 오류가 발생했습니다. 다시 시도해 주세요."}}]
            }
        }


@app.get("/")
def health_check():
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
