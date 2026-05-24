import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database import supabase

async def recommend_jobs_fallback_local(user_embedding: list, limit: int = 5):
    """
    Supabase RPC 호출 실패 시 로컬에서 3개 테이블의 임베딩 유사도를 계산하여
    상위 공고를 추천하는 robust fallback 함수.
    """
    tables = ["jobs", "jobs3", "job_seoul_50"]
    combined_jobs = []
    
    for table in tables:
        try:
            res = supabase.table(table).select("*").not_.is_("embedding", "null").limit(30).execute()
            for row in res.data:
                row["_source_table"] = table
                combined_jobs.append(row)
        except Exception as table_err:
            print(f"[추천 로컬 fallback] {table} 조회 실패: {table_err}")
            
    if not combined_jobs:
        return []
        
    scored = []
    u_vec = user_embedding
    
    for job in combined_jobs:
        j_vec = job.get("embedding")
        if not j_vec or len(j_vec) != len(u_vec):
            continue
        # 단순 내적 (cosine similarity)
        similarity = sum(x * y for x, y in zip(u_vec, j_vec))
        # UI 매칭률 표시를 위해 적합한 범위로 유사도 보정
        job["similarity"] = max(0.0, min(1.0, similarity))
        # 벡터 출력을 하나하나 찍지 않도록 계산이 끝난 후 embedding 필드를 제거합니다.
        job.pop("embedding", None)
        scored.append((job, similarity))
        
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item[0] for item in scored[:limit]]


async def recommend_jobs_for_user(user_id: str, limit: int = 5):
    """
    주어진 user_id의 임베딩 벡터를 가져와서,
    3개의 공고 테이블(jobs, jobs3, job_seoul_50)을 통합 검색하는 RPC 함수를 호출합니다.
    """
    try:
        # 1. 유저 정보를 DB에서 가져옵니다.
        user_res = supabase.table("users").select("*").eq("user_id", user_id).limit(1).execute()
        
        user_embedding = None
        
        # 카카오 오픈빌더의 '봇 테스트' 환경에서는 가짜 user_id가 들어옵니다.
        # 테스트를 쉽게 하기 위해, 유저를 못 찾으면 DB에서 임베딩이 설정된 아무 유저나 한 명 골라서 테스트용으로 씁니다!
        if not user_res.data:
            print(f"[추천 알림] {user_id} 유저가 없어 임의의 가짜 유저(페르소나)로 테스트를 진행합니다.")
            random_user_res = supabase.table("users").select("embedding").not_.is_("embedding", "null").limit(1).execute()
            if not random_user_res.data:
                 print("[추천 오류] DB에 페르소나 데이터가 하나도 없습니다.")
                 return []
            user_embedding = random_user_res.data[0].get("embedding")
        else:
            user_data = user_res.data[0]
            user_embedding = user_data.get("embedding")
            
            # 만약 유저의 임베딩이 없으면, 온보딩 프로필 정보를 합쳐서 실시간 생성 및 저장
            if not user_embedding:
                print(f"[추천 알림] {user_id} 유저의 임베딩이 없어 실시간 생성합니다.")
                user_text = (
                    f"희망직무: {user_data.get('desired_job') or ''}, "
                    f"보유기술: {user_data.get('skills') or ''}, "
                    f"경력사항: {user_data.get('career') or ''}, "
                    f"핵심강점: {user_data.get('strengths') or ''}, "
                    f"희망지역: {user_data.get('location') or ''}"
                )
                try:
                    from database import embeddings
                    # aembed_query는 비동기 함수이므로 await 적용
                    user_embedding = await embeddings.aembed_query(user_text)
                    # DB에 저장해서 캐싱
                    supabase.table("users").update({"embedding": user_embedding}).eq("user_id", user_id).execute()
                    print(f"[추천 알림] {user_id} 유저의 프로필 임베딩 실시간 생성 및 캐싱 완료")
                except Exception as e_embed:
                    print(f"[추천 오류] 유저 임베딩 실시간 생성 실패: {e_embed}")

        if not user_embedding:
            print(f"[추천 오류] 임베딩 벡터가 존재하지 않습니다.")
            return []

        # 2. 통합 검색 RPC 함수 호출 (match_jobs_hybrid)
        # 이 함수는 DB에 먼저 생성되어 있어야 합니다.
        try:
            search_res = supabase.rpc(
                "match_jobs_hybrid",
                {
                    "query_embedding": user_embedding,
                    "match_count": limit
                }
            ).execute()
            jobs_data = search_res.data
        except Exception as rpc_err:
            print(f"[추천 RPC 실패] match_jobs_hybrid 호출 에러: {rpc_err}. 로컬 Fallback 유사도 추천을 가동합니다.")
            jobs_data = await recommend_jobs_fallback_local(user_embedding, limit)

        return jobs_data

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
        company = job.get("company") or job.get("company_name") or job.get("company_or_org") or "기업명 비공개"
        location = job.get("location") or job.get("event_location") or "지역 미상"
        similarity = job.get("similarity", 0)
        url = job.get("url") or job.get("source_url") or "https://www.work.go.kr/"
        
        # 카카오톡 기본 카드 형식
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
