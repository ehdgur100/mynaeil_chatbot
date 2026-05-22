from typing import Dict, Any
from state import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from nodes.base import llm_fast
import database.operations as db_ops
from services.worknet_api import WorknetAPIClient
from services.crawler import SeniorJobCrawler
from services.recommender import content_based_filtering
import config

async def job_search(state: AgentState) -> Dict[str, Any]:
    """
    [엔지니어 A 담당] 사용자의 위치와 희망 직종을 연동하여 맞춤형 일자리를 찾고 매칭하는 노드.
    사용자 입력에서 키워드와 지역을 추출한 후, 추천 필터링 알고리즘(content_based_filtering)을 거쳐 정제합니다.
    """
    print("[Node] job_search 실행")
    user_id = state.get("user_id", "unknown")
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else ""

    # 1. 사용자 온보딩 프로필 정보 조회
    profile = db_ops.get_user_profile(user_id) or {}
    desired_job = profile.get("desired_job", "")
    location = profile.get("location", "")

    # 2. llm_fast 모델을 사용해 사용자 입력 발화에서 검색 키워드와 지역을 동적으로 추출
    extract_prompt = (
        "사용자가 찾고자 하는 구인/구직 '키워드'(직무)와 희망 '지역'(구/시/도 단위)을 아래 JSON 포맷으로 추출하세요.\n"
        "반드시 JSON 형태로만 응답하고 백틱(```) 등은 포함하지 마십시오.\n"
        "예: '마포구에서 경비 일자리 찾아주세요' -> {\"keyword\": \"경비\", \"location\": \"서울 마포구\"}\n"
        "찾을 수 없는 항목은 빈 문자열(\"\")로 기재하세요."
    )
    
    try:
        response = await llm_fast.ainvoke([
            SystemMessage(content=extract_prompt),
            HumanMessage(content=user_input)
        ])
        import json
        import re
        
        # response.content가 리스트 구조로 들어오는 경우를 위한 방어 코드 추가
        content_val = response.content
        if isinstance(content_val, list):
            content_str = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content_val])
        else:
            content_str = str(content_val)

        # JSON 문자열만 정규식으로 정제
        cleaned = re.search(r'\{.*\}', content_str.strip(), re.DOTALL)
        if cleaned:
            extracted = json.loads(cleaned.group(0))
        else:
            extracted = {"keyword": "", "location": ""}
    except Exception as e:
        print(f"[Job Extract Error] {e}")
        extracted = {"keyword": "", "location": ""}

    search_keyword = extracted.get("keyword") or desired_job or "시니어"
    search_location = extracted.get("location") or location or "서울"

    # 3. 데이터 원천 수집 (API 클라이언트 및 크롤러 뼈대 구동)
    # A. API 연동
    worknet_client = WorknetAPIClient(auth_key=getattr(config, "WORKNET_API_KEY", ""))
    api_jobs = await worknet_client.get_jobs_by_keyword(search_keyword, location=search_location)

    # B. 크롤러 연동
    crawler = SeniorJobCrawler()
    crawled_jobs = crawler.crawl_senior_jobs(limit=5)
    
    # 두 소스의 일자리 리스트 병합
    all_jobs = []
    # 중복 제거를 고려한 리스트 채우기
    seen_titles = set()
    for job in api_jobs + crawled_jobs:
        title = job.get("title")
        if title not in seen_titles:
            seen_titles.add(title)
            # recommender.py 가 사용할 카테고리 필드 추가
            if "job_category" not in job:
                job["job_category"] = search_keyword
            all_jobs.append(job)

    # 4. 추천 필터링 적용 (content_based_filtering 활용)
    # 사용자 프로필이 채워져 있을수록 추천 정확도가 올라갑니다.
    recommended = content_based_filtering(profile, all_jobs, top_n=3)

    # 5. 출력 메시지 조립
    if recommended:
        job_list_str = ""
        for i, job in enumerate(recommended):
            job_list_str += (
                f"📌 {i+1}. {job.get('title')}\n"
                f"  - 업체명: {job.get('company')}\n"
                f"  - 지역: {job.get('location')}\n"
                f"  - 급여: {job.get('salary', '협의')}\n"
                f"  - 기한: {job.get('deadline', '채용시까지')}\n"
                f"  - 공고링크: {job.get('url')}\n\n"
            )
        
        ai_response = (
            f"🔍 '{search_location}' 지역의 '{search_keyword}' 관련 신중년 일자리 검색 결과입니다!\n\n"
            f"{job_list_str.strip()}\n\n"
            f"💡 상세 정보 확인 및 지원은 공고링크를 통해 워크넷 등에서 가능합니다. "
            f"원하시는 지역이나 직무를 더 구체적으로 말씀해 주시면 맞춤 공고를 매칭해 드릴게요!"
        )
    else:
        ai_response = (
            f"죄송합니다. 현재 '{search_location}' 지역의 '{search_keyword}' 일자리 모집 공고를 찾지 못했습니다. 😥\n\n"
            f"구직 등록을 해 두시면 적합한 일자리가 나오는 대로 매칭 안내해 드릴게요. "
            f"다른 직무나 관심 지역을 말씀해 주시겠어요?"
        )

    # 6. 빠른 답장 버튼(Quick Replies) 생성
    quick_replies = ["자소서 작성", "정부지원금 알아보기", "직업교육 추천"]
    kakao_resp = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": ai_response}}],
            "quickReplies": [
                {"action": "message", "label": label, "messageText": label}
                for label in quick_replies
            ]
        }
    }

    return {
        "messages": [AIMessage(content=ai_response)],
        "kakao_response": kakao_resp,
        "intent": "job_search"
    }
