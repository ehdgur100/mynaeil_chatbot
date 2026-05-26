import os
import sys
from typing import List, Dict, Any

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database.connection import supabase

def content_based_filtering(user_profile: Dict[str, Any], jobs: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """
    [콘텐츠 기반 필터링 (CB)]
    사용자의 희망 직무, 경력, 자격증, 강점 키워드와 공고 텍스트 간 단어 매칭 유사도를 구해 추천합니다.
    """
    if not user_profile or not jobs:
        return jobs[:top_n]

    user_words = []
    for field in ["desired_job", "career", "skills", "strengths"]:
        val = user_profile.get(field)
        if val:
            user_words.extend([w.strip() for w in val.replace(",", " ").split() if w.strip()])

    scored_jobs = []
    desired_job = user_profile.get("desired_job") or ""
    desired_job_tokens = [w.strip() for w in desired_job.replace(",", " ").split() if w.strip()]

    for job in jobs:
        title = job.get("title") or job.get("job_title") or ""
        content = job.get("content") or job.get("description") or ""
        category = job.get("job_category") or ""
        job_text = f"{title} {content} {category}"
        
        score = 0.0
        for word in user_words:
            if word in job_text:
                if word in desired_job_tokens:
                    score += 5.0
                else:
                    score += 1.0
                    
        user_loc = user_profile.get("location", "")
        job_loc = job.get("location") or job.get("event_location") or ""
        if user_loc and job_loc and (user_loc in job_loc or job_loc in user_loc):
            score += 3.0

        job["similarity"] = score  # 유사도 점수 임시 기록
        scored_jobs.append((job, score))

    scored_jobs.sort(key=lambda x: x[1], reverse=True)
    
    # 얕은 복사(shallow copy) 방지를 위해 dict 객체들을 새로 생성해 반환
    return [dict(item[0]) for item in scored_jobs[:top_n]]

def collaborative_filtering(user_id: str, active_users: List[Dict[str, Any]], jobs: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """
    [협업 필터링 (CF)]
    나와 프로필(희망직무, 지역, 조건)이 유사한 이웃 유저들이 선호하는 공고군 매칭 추천을 수행합니다.
    """
    target_user = next((u for u in active_users if u.get("user_id") == user_id), None)
    if not target_user or len(active_users) <= 1:
        return jobs[:top_n]

    user_similarities = []
    for other_user in active_users:
        if other_user.get("user_id") == user_id:
            continue
        
        sim_score = 0
        if other_user.get("desired_job") == target_user.get("desired_job"):
            sim_score += 3
        if other_user.get("location") == target_user.get("location"):
            sim_score += 2
        if other_user.get("work_condition") == target_user.get("work_condition"):
            sim_score += 1
            
        user_similarities.append((other_user, sim_score))

    user_similarities.sort(key=lambda x: x[1], reverse=True)
    neighbors = [item[0] for item in user_similarities[:3]]

    recommended_jobs = []
    # 중복 삽입 방지를 위한 세트
    seen_job_titles = set()
    
    for neighbor in neighbors:
        for job in jobs:
            category = job.get("job_category") or ""
            title = job.get("title") or ""
            if neighbor.get("desired_job") and neighbor.get("desired_job") in category:
                if title not in seen_job_titles:
                    seen_job_titles.add(title)
                    # 유사 유저 선호도에 따른 보너스 스코어 부여
                    job["similarity"] = job.get("similarity", 0.0) + 2.0
                    recommended_jobs.append(job)

    if not recommended_jobs:
        return jobs[:top_n]
        
    recommended_jobs.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
    return recommended_jobs[:top_n]

async def recommend_jobs_for_user(user_id: str, limit: int = 5) -> list:
    """
    콘텐츠 기반 필터링(CB)과 협업 필터링(CF)을 하이브리드로 결합하여 맞춤 공고를 추천합니다.
    """
    try:
        if supabase is None:
            return []

        # 1. 대상 유저 정보 가져오기
        user_res = supabase.table("users").select("*").eq("user_id", user_id).limit(1).execute()
        
        if not user_res.data:
            print(f"[추천 API] {user_id} 유저가 없어 임의의 페르소나 유저로 대체합니다.")
            random_user_res = supabase.table("users").select("*").limit(1).execute()
            if not random_user_res.data:
                return []
            user_data = random_user_res.data[0]
        else:
            user_data = user_res.data[0]

        # 2. 전체 활성 유저 프로필 가져오기 (CF 연산용)
        active_users_res = supabase.table("users").select("*").limit(100).execute()
        active_users = active_users_res.data or []

        # 3. 3대 테이블 공고 풀(Pool) 확보
        combined_jobs = []
        for table in ["jobs", "jobs3", "job_seoul_50"]:
            try:
                res = supabase.table(table).select("*").limit(40).execute()
                for row in res.data:
                    row["_source_table"] = table
                    # 컬럼 다형성 표준화
                    if table == "job_seoul_50":
                        row["company"] = row.get("company_or_org") or "기업명 비공개"
                        row["title"] = row.get("occupation_name") or "제목 없음"
                        row["content"] = row.get("occupation_name") or ""
                        row["url"] = row.get("source_url") or "https://www.50plus.or.kr/"
                        row["location"] = row.get("event_location") or "서울"
                        row["salary"] = row.get("pay_text") or "협의"
                        row["deadline"] = row.get("apply_end") or "채용시까지"
                    else:
                        row["company"] = row.get("company") or row.get("company_name") or "기업명 비공개"
                        row["title"] = row.get("title") or "제목 없음"
                        row["content"] = row.get("content") or row.get("description") or ""
                        row["url"] = row.get("url") or "https://www.work.go.kr/"
                        row["location"] = row.get("location") or "지역 미상"
                        row["salary"] = row.get("salary") or "협의"
                        row["deadline"] = row.get("deadline") or "채용시까지"
                    
                    combined_jobs.append(row)
            except Exception as e:
                print(f"[추천 데이터 로드 실패] {table}: {e}")

        if not combined_jobs:
            return []

        # 4. 콘텐츠 기반 필터링 (CB) 적용 - 전체 공고 풀에서 상위 limit * 2개 추출
        cb_candidates = content_based_filtering(user_data, combined_jobs, top_n=limit * 2)

        # 5. 협업 필터링 (CF) 적용 - CB 후보군에 대해 다른 유사 유저 선호도를 얹어 최종 정렬
        cf_candidates = collaborative_filtering(user_id, active_users, cb_candidates, top_n=limit)

        # UI 출력용으로 similarity 값 정밀 보정 (0.5 ~ 0.98 범위로 매칭률 스케일링)
        max_score = max([j.get("similarity", 1.0) for j in cf_candidates]) if cf_candidates else 1.0
        for job in cf_candidates:
            score = job.get("similarity", 1.0)
            ratio = score / (max_score if max_score > 0 else 1.0)
            job["similarity"] = max(0.65, min(0.98, ratio * 0.98))

        return cf_candidates

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
