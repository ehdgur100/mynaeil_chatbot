import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database import supabase

async def recommend_jobs_for_user(user_id: str, limit: int = 5):
    """
    주어진 user_id의 임베딩 벡터를 가져와서,
    3개의 공고 테이블(jobs, jobs3, job_seoul_50)을 통합 검색하는 RPC 함수를 호출합니다.
    """
    try:
        # 1. 유저의 벡터를 DB에서 가져옵니다.
        user_res = supabase.table("users").select("embedding").eq("user_id", user_id).limit(1).execute()
        
        # 카카오 오픈빌더의 '봇 테스트' 환경에서는 가짜 user_id가 들어옵니다. 
        # 테스트를 쉽게 하기 위해, 유저를 못 찾으면 DB에서 아무 유저나 한 명 골라서 테스트용으로 씁니다!
        if not user_res.data:
            print(f"[추천 알림] {user_id} 유저가 없어 임의의 가짜 유저(페르소나)로 테스트를 진행합니다.")
            random_user_res = supabase.table("users").select("embedding").limit(1).execute()
            if not random_user_res.data:
                 print("[추천 오류] DB에 페르소나 데이터가 하나도 없습니다.")
                 return []
            user_embedding = random_user_res.data[0].get("embedding")
        else:
            user_embedding = user_res.data[0].get("embedding")

        if not user_embedding:
            print(f"[추천 오류] 임베딩 벡터가 존재하지 않습니다.")
            return []

        # 2. 통합 검색 RPC 함수 호출 (match_jobs_hybrid)
        # 이 함수는 DB에 먼저 생성되어 있어야 합니다.
        search_res = supabase.rpc(
            "match_jobs_hybrid",
            {
                "query_embedding": user_embedding,
                "match_count": limit
            }
        ).execute()

        return search_res.data

    except Exception as e:
        print(f"[추천 로직 예외 발생] {e}")
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
        # 각 일자리 테이블마다 컬럼명이 조금씩 다를 수 있으므로 안전하게 get() 사용
        title = job.get("title") or job.get("job_title") or "제목 없음"
        company = job.get("company") or job.get("company_name") or "기업명 비공개"
        location = job.get("location") or "지역 미상"
        similarity = job.get("similarity", 0)
        
        # 카카오톡 기본 카드 형식
        item = {
            "title": f"[{company}] {title}",
            "description": f"📍 위치: {location}\n✨ 매칭률: {int(similarity * 100)}%",
            "buttons": [
                {
                    "action": "webLink",
                    "label": "공고 상세보기",
                    "webLinkUrl": "https://www.work.go.kr/"  # 실제 링크는 데이터에 맞게 수정 필요
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
