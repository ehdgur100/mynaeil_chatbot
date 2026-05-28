import re
import sys
from html import escape

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse
from langchain_core.messages import HumanMessage

from database.connection import supabase
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
            # 리셋 키워드와 메뉴 선택 버튼은 빠른 처리 대상
            skip_keywords = ["처음부터", "초기화", "다시 시작", "이어서 작성하기", "이어서 자소서 작성하기"]



            if step == 8 and not any(k in input_clean for k in skip_keywords):
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


@app.get("/jobs3/wanted/{wanted_auth_no}", response_class=HTMLResponse)
def jobs3_detail_page(wanted_auth_no: str):
    if supabase is None:
        return HTMLResponse("Supabase 연결이 설정되지 않았습니다.", status_code=500)

    result = (
        supabase.table("jobs3")
        .select(
            "title,company,content,location,salary,career_required,"
            "employment_type,job_category,deadline,apply_method,external_id"
        )
        .eq("external_id", wanted_auth_no)
        .limit(1)
        .execute()
    )
    if not result.data:
        result = (
            supabase.table("jobs3")
            .select(
                "title,company,content,location,salary,career_required,"
                "employment_type,job_category,deadline,apply_method,external_id"
            )
            .ilike("url", f"%{wanted_auth_no}%")
            .limit(1)
            .execute()
        )

    if not result.data:
        return HTMLResponse("공고 정보를 찾을 수 없습니다.", status_code=404)

    job = result.data[0]
    title = escape(str(job.get("title") or "서울시 일자리 공고"))
    company = escape(str(job.get("company") or "기업명 확인 필요"))
    content = escape(str(job.get("content") or "상세 내용 확인 필요"))
    seoul_list_url = "https://job.seoul.go.kr/hmpg/rmim/rsmg/rsmgListPage.do"
    work24_url = "https://www.work24.go.kr"

    meta_items = [
        ("근무지역", job.get("location")),
        ("급여", job.get("salary")),
        ("경력", job.get("career_required")),
        ("고용형태", job.get("employment_type")),
        ("직종", job.get("job_category")),
        ("마감일", job.get("deadline")),
        ("접수방법", job.get("apply_method")),
    ]
    meta_html = "\n".join(
        f"<li><strong>{escape(label)}</strong><span>{escape(str(value))}</span></li>"
        for label, value in meta_items
        if value
    )

    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #17202a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
      padding: 32px 18px 56px;
    }}
    .panel {{
      background: #fff;
      border: 1px solid #dde2e8;
      border-radius: 8px;
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 26px;
      line-height: 1.35;
    }}
    .company {{
      margin: 0 0 22px;
      color: #52616f;
      font-size: 16px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 0 0 26px;
    }}
    .actions a {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 15px;
      border-radius: 6px;
      text-decoration: none;
      font-weight: 700;
    }}
    .primary {{
      background: #1769e0;
      color: #fff;
    }}
    .secondary {{
      background: #eef3f8;
      color: #213142;
      border: 1px solid #d6dee8;
    }}
    ul {{
      list-style: none;
      padding: 0;
      margin: 0 0 26px;
      border-top: 1px solid #edf0f3;
    }}
    li {{
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 12px;
      padding: 10px 0;
      border-bottom: 1px solid #edf0f3;
    }}
    li strong {{
      color: #2f3b45;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: keep-all;
      overflow-wrap: anywhere;
      margin: 0;
      font: inherit;
    }}
    .source {{
      margin-top: 24px;
      color: #697785;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>{title}</h1>
      <p class="company">{company}</p>
      <div class="actions">
        <a class="primary" href="{seoul_list_url}" target="_blank" rel="noopener noreferrer">서울시 일자리포털</a>
        <a class="secondary" href="{work24_url}" target="_blank" rel="noopener noreferrer">고용24 바로가기</a>
      </div>
      <ul>{meta_html}</ul>
      <pre>{content}</pre>
      <p class="source">
        자료 출처: 서울시 일자리 API / 구인신청번호 {escape(wanted_auth_no)}<br>
        일부 서울시 원문 상세 페이지는 제목과 본문이 비어 보일 수 있어, 이 페이지에서 API 상세 내용을 함께 제공합니다.
      </p>
    </section>
  </main>
</body>
</html>"""
    return HTMLResponse(html)
