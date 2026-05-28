import os
import sys
import asyncio
from typing import List, Dict, Any

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database.connection import supabase
from database.vector_search import embeddings


def _build_user_query(user: dict) -> str:
    """
    사용자 프로필을 채용공고 형식의 텍스트로 변환합니다.
    프로필 나열 형식("희망직무: 경비") 대신 공고 텍스트와 유사한 자연어 형식으로
    작성해야 임베딩 공간에서 공고 벡터와 가까워져 유사도 정확도가 높아집니다.
    """
    desired_job = user.get("desired_job", "")
    location = user.get("location", "")
    career = user.get("career", "")
    skills = user.get("skills", "")
    work_condition = user.get("work_condition", "")
    strengths = user.get("strengths", "")

    lines = []

    # 공고 제목 형식: "서울 강서구 경비 채용"
    title_parts = [p for p in [location, desired_job] if p]
    if title_parts:
        lines.append(" ".join(title_parts) + " 채용")

    # 경력 사항
    if career:
        lines.append(career)

    # 자격증 (없음 응답은 제외)
    if skills and skills not in ("없음", "없어요", "없습니다"):
        lines.append(skills)

    # 근무 조건
    if work_condition:
        lines.append(work_condition)

    # 강점/특기
    if strengths:
        lines.append(strengths)

    return "\n".join(lines) if lines else "구직자 채용"


def _filter_by_location(jobs: list, user_location: str) -> list:
    """지역 토큰 기반으로 공고를 필터링합니다. 구·시 단위로 비교합니다."""
    # "서울 영등포구" → ["서울", "영등포구"] 로 분리해 구 레벨 매칭
    loc_tokens = [t for t in user_location.replace(",", " ").split() if len(t) > 1]
    if not loc_tokens:
        return jobs
    return [
        job for job in jobs
        if any(token in (job.get("location") or "") for token in loc_tokens)
    ]


async def recommend_jobs_for_user(user_id: str, limit: int = 5) -> list:
    """
    match_jobs_hybrid RPC를 사용한 벡터 유사도 기반 공고 추천.
    사용자 프로필 텍스트를 임베딩하여 3개 테이블 전체에서 의미적으로 가장 가까운 공고를 반환합니다.
    """
    try:
        if supabase is None:
            return []

        # 1. 유저 프로필 조회
        user_res = supabase.table("users").select("*").eq("user_id", user_id).limit(1).execute()
        if not user_res.data:
            print(f"[추천] {user_id} 유저 없음")
            return []
        user_data = user_res.data[0]

        # 2. 프로필 → 쿼리 텍스트 → 임베딩 벡터
        query_text = _build_user_query(user_data)
        print(f"[추천] 쿼리 텍스트: {query_text[:80]}...")
        query_vector = await embeddings.aembed_query(query_text)

        # 3. match_jobs_hybrid RPC 호출 (지역 필터 후 충분한 결과 확보를 위해 limit*4 요청)
        result = await asyncio.to_thread(
            lambda: supabase.rpc(
                "match_jobs_hybrid",
                {
                    "query_embedding": query_vector,
                    "match_count": limit * 4,
                }
            ).execute()
        )

        jobs = result.data or []
        print(f"[추천] 벡터 검색 결과: {len(jobs)}건")

        # 4. 지역 후처리 필터
        user_location = user_data.get("location", "")
        if user_location:
            filtered = _filter_by_location(jobs, user_location)
            print(f"[추천] 지역 필터({user_location}) 후: {len(filtered)}건")
            # 필터 후 결과가 limit 이상이면 사용, 부족하면 필터 없이 전체 사용
            if len(filtered) >= limit:
                jobs = filtered

        return jobs[:limit]

    except Exception as e:
        print(f"[추천 로직 통합 예외] {e}")
        return []


def build_kakao_carousel_response(jobs: list) -> dict:
    """
    가져온 공고 리스트를 카카오톡 챗봇의 캐러셀(Carousel) 형태로 변환합니다.
    """
    if not jobs:
        return {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": "현재 맞춤 추천 공고를 찾지 못했습니다. 😥"}}]
            }
        }

    items = []
    for job in jobs:
        title = job.get("title") or "제목 없음"
        company = job.get("company") or "기업명 비공개"
        location = job.get("location") or "지역 미상"
        similarity = job.get("similarity", 0.0)
        url = job.get("url") or "https://www.work.go.kr/"

        item = {
            "title": f"[{company}] {title}",
            "description": f"📍 위치: {location}\n✨ 매칭률: {int(similarity * 100)}%",
            "buttons": [
                {
                    "action": "webLink",
                    "label": "공고 상세보기",
                    "webLinkUrl": url
                }
            ]
        }
        items.append(item)

    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "carousel": {
                        "type": "basicCard",
                        "items": items
                    }
                }
            ]
        }
    }
