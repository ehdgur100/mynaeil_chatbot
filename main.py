from fastapi import FastAPI, BackgroundTasks, Request
from langchain_core.messages import HumanMessage
from graph import app_graph
import database.operations as db_ops
import httpx
import asyncio

app = FastAPI(title="나의내일 챗봇 API")

# 카카오톡 서버나 챗봇 로직 내부에서 오류 발생 시 유저에게 반환할 기본 안내 템플릿입니다.
_ERROR_BODY = {
    "version": "2.0",
    "template": {
        "outputs": [{"simpleText": {"text": "처리 도중 오류가 발생했어요. 다시 시도해 주세요 😥"}}]
    },
}

def is_slow_request(user_id: str, user_message: str) -> tuple[bool, str]:
    """
    [느린 작업 판별기]
    사용자의 입력 메시지와 프로필 상태를 분석해서,
    답변을 만드는 데 5초 이상 오래 걸리는 무거운 작업(자소서 생성/검증 등)인지 확인합니다.
    """
    input_clean = user_message.strip().lower()
    
    # 1. 유튜브 팁 RAG 기반의 자소서 검증(resume_verify) 요청인지 체크
    if any(k in input_clean for k in ["검증", "평가", "첨삭", "피드백", "판별"]):
        return True, "자소서를 유튜브 팁 기반으로 분석하는 중이에요. 잠시만 기다려주세요 🔍"
        
    # 2. 온보딩 7개의 질문을 모두 마친 상태에서 마지막 자소서를 만드는 시점인지 체크
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
    print(f"[Background] 랭그래프 비동기 처리 시작 (User: {user_id[:16]}, Callback: {callback_url})")
    
    config_dict = {"configurable": {"thread_id": user_id}}
    
    # 이전 대화 턴의 의도(intent)와 응답(kakao_response)이 현재 턴에 영향을 주지 않도록 초기화해 줍니다.
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "intent": None,
        "kakao_response": None,
        "callback_url": callback_url
    }
    
    try:
        # LangGraph 워크플로우 실행
        final_state = await app_graph.ainvoke(initial_state, config=config_dict)
        kakao_resp = final_state.get("kakao_response")
        
        # 챗봇 방에서 리치 템플릿(kakao_response)을 만들어내지 못한 경우, 텍스트 메시지를 기본값으로 감싸줍니다.
        if not kakao_resp:
            last_msg = final_state["messages"][-1].content if final_state.get("messages") else "처리가 완료되었습니다."
            kakao_resp = {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": last_msg}}]}
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
        background_tasks.add_task(run_graph_in_background, user_id, user_message, callback_url)
        return {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": wait_msg},
        }

    # 2. 동기 처리 (가벼운 일상대화 / 콜백 미지원 환경 대응)
    config_dict = {"configurable": {"thread_id": user_id}}
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "intent": None,
        "kakao_response": None,
        "callback_url": callback_url
    }

    try:
        # 동기적으로 즉시 랭그래프를 호출하여 결과를 수신 및 반환합니다.
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
    """챗봇 서버 상태 모니터링용 엔드포인트"""
    return {"status": "ok", "message": "나의내일 챗봇 서버가 정상 작동 중입니다."}
