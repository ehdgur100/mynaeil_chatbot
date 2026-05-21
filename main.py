from fastapi import FastAPI, BackgroundTasks, Request
from langchain_core.messages import HumanMessage
from graph import app_graph
import database.operations as db_ops
import httpx
import asyncio

app = FastAPI(title="나의내일 챗봇 API")

_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [{"simpleText": {"text": "처리 도중 오류가 발생했어요. 다시 시도해 주세요 😥"}}]
    },
}

def is_slow_request(user_id: str, user_message: str) -> tuple[bool, str]:
    """
    사용자의 입력과 프로필 상태를 분석해 시간이 많이 걸리는 작업(5초 초과)인지 판별하고
    적절한 대기 메시지를 반환합니다.
    """
    input_clean = user_message.strip().lower()
    
    # 1. RAG 기반 자소서 검증 (resume_verify) 의도 체크
    if any(k in input_clean for k in ["검증", "평가", "첨삭", "피드백", "판별"]):
        return True, "자소서를 유튜브 팁 기반으로 분석하는 중이에요. 잠시만 기다려주세요 🔍"
        
    # 2. 자소서 생성 (resume_gen) 온보딩 종료 시점 혹은 이전 정보로 작성 요청 시 체크
    try:
        profile = db_ops.get_user_profile(user_id)
        if profile:
            step = profile.get("step", 0)
            # 마지막 단계(6단계)에서 답변을 등록하는 중
            if step == 6 and input_clean != "처음부터":
                return True, "자기소개서를 작성 중이에요. 잠시만 기다려주세요 ✍️"
            # 온보딩 완료 상태에서 이전 정보 재작성 요청
            if step >= 7 and input_clean == "이전 정보로 자소서 작성하기":
                return True, "자기소개서를 작성 중이에요. 잠시만 기다려주세요 ✍️"
    except Exception as e:
        print(f"[is_slow_request Warning] 유저 프로필 조회 실패: {e}")
        
    return False, ""

async def run_graph_in_background(user_id: str, user_message: str, callback_url: str):
    """
    느린 작업군에 대해 백그라운드 태스크로 LangGraph를 수행하고 결과를 카카오톡 콜백으로 전송합니다.
    """
    print(f"[Background] 랭그래프 비동기 처리 시작 (User: {user_id[:16]}, Callback: {callback_url})")
    
    config_dict = {"configurable": {"thread_id": user_id}}
    # 이전 턴의 intent와 response를 명시적으로 초기화(None)하여 상태 유출을 방지합니다.
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "intent": None,
        "kakao_response": None,
        "callback_url": callback_url
    }
    
    try:
        final_state = await app_graph.ainvoke(initial_state, config=config_dict)
        kakao_resp = final_state.get("kakao_response")
        
        # 노드에서 포맷팅된 카카오 응답이 없는 경우 텍스트 기반 fallback 제공
        if not kakao_resp:
            last_msg = final_state["messages"][-1].content if final_state.get("messages") else "처리가 완료되었습니다."
            kakao_resp = {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": last_msg}}]}
            }
            
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=kakao_resp, timeout=10.0)
            print(f"[Background] 콜백 전송 성공 (상태코드: {resp.status_code})")
    except Exception as e:
        print(f"[Background Error] 비동기 그래프 처리 중 예외 발생: {e}")
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

    # 1. 5초 초과 위험 작업 및 콜백 URL 존재 시 비동기 처리
    slow, wait_msg = is_slow_request(user_id, user_message)
    if slow and callback_url:
        background_tasks.add_task(run_graph_in_background, user_id, user_message, callback_url)
        return {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": wait_msg},
        }

    # 2. 동기 처리 (빠른 대화 / 콜백 미지원 환경 대응)
    config_dict = {"configurable": {"thread_id": user_id}}
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "intent": None,
        "kakao_response": None,
        "callback_url": callback_url
    }

    try:
        final_state = await app_graph.ainvoke(initial_state, config=config_dict)
        kakao_resp = final_state.get("kakao_response")
        
        if not kakao_resp:
            last_msg = final_state["messages"][-1].content if final_state.get("messages") else "답변을 준비하지 못했습니다."
            kakao_resp = {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": last_msg}}]}
            }
        return kakao_resp
    except Exception as e:
        print(f"[Sync Process Error] 동기 그래프 처리 실패: {e}")
        return _ERROR_BODY

@app.get("/")
def health_check():
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
