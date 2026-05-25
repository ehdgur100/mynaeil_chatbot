from typing import Optional
from database.connection import supabase

def get_user_profile(user_id: str) -> Optional[dict]:
    """사용자의 온보딩 정보를 조회합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    result = supabase.table("users").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None

def create_user_profile(user_id: str) -> None:
    """새로운 사용자의 온보딩 프로필을 생성합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    supabase.table("users").insert({"user_id": user_id, "step": 0}).execute()

def save_onboarding_answer(user_id: str, field: str, answer: str, next_step: int) -> None:
    """사용자의 온보딩 답변과 다음 단계를 저장합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    supabase.table("users").update(
        {field: answer, "step": next_step}
    ).eq("user_id", user_id).execute()

def reset_user_profile(user_id: str) -> None:
    """사용자의 온보딩 상태를 처음부터로 초기화합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    supabase.table("users").upsert({
        "user_id": user_id, "step": 0,
        "career": None, "skills": None, "desired_job": None,
        "location": None, "work_condition": None,
        "strengths": None, "goal": None,
    }).execute()

def save_resume(user_id: str, desired_job: str, content: str) -> None:
    """작성 또는 검증 완료된 자기소개서를 DB에 저장합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    # 기존 자소서 삭제 후 신규 등록 (1명당 1개 유지 규칙)
    supabase.table("resumes").delete().eq("user_id", user_id).execute()
    supabase.table("resumes").insert({
        "user_id": user_id,
        "desired_job": desired_job,
        "content": content,
    }).execute()

def get_resume(user_id: str) -> Optional[dict]:
    """사용자의 저장된 자기소개서를 조회합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    result = supabase.table("resumes").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None

def get_job_by_id(job_id: str) -> Optional[dict]:
    """jobs3 → jobs → job_seoul_50 순서로 ID로 공고를 조회하고 정규화된 dict를 반환합니다."""
    if supabase is None:
        return None
    for table in ("jobs3", "jobs", "job_seoul_50"):
        try:
            result = supabase.table(table).select("*").eq("id", job_id).limit(1).execute()
            if result.data:
                row = result.data[0]
                return {
                    "job_id": row.get("id"),
                    "table": table,
                    "company": row.get("company") or row.get("company_name") or "",
                    "title": row.get("title") or row.get("job_category") or "",
                    "description": row.get("content") or row.get("description") or "",
                    "location": row.get("location") or "",
                    "deadline": row.get("deadline") or row.get("end_date") or "",
                    "source_url": row.get("source_url") or row.get("url") or "",
                }
        except Exception as e:
            print(f"[get_job_by_id] {table} 조회 실패: {e}")
    return None

def get_jobs_from_db(keyword: str, location: str, limit: int = 10) -> list[dict]:
    """미리 크롤링하여 저장해 둔 jobs3 테이블에서 키워드와 지역에 맞는 일자리 공고를 가져옵니다."""
    if supabase is None:
        return []
    try:
        query = supabase.table("jobs3").select("*")
        
        # 키워드 매칭 조건 구성
        filter_conditions = []
        if keyword:
            # 카테고리 기호('·', '/') 등이 포함된 복합 키워드를 공백으로 쪼개서 각각 OR 검색을 수행하도록 고도화
            # 예: '청소·환경미화' -> ['청소', '환경미화']
            sub_keywords = [k.strip() for k in keyword.replace("·", " ").replace("/", " ").split() if k.strip()]
            for kw in sub_keywords:
                filter_conditions.append(f"job_category.ilike.%{kw}%")
                filter_conditions.append(f"title.ilike.%{kw}%")
                filter_conditions.append(f"content.ilike.%{kw}%")
            
        # 지역 매칭 조건 구성
        if location and location not in ("서울", "경기", "전국"):
            loc_clean = location.replace("서울 ", "").replace("경기 ", "").strip()
            query = query.ilike("location", f"%{loc_clean}%")
            
        if filter_conditions:
            or_filter = ",".join(filter_conditions)
            query = query.or_(or_filter)
            
        result = query.limit(limit).execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"[DB Job Search Error] {e}")
        return []

def get_courses_from_db(subject: str, location: str, limit: int = 5) -> list[dict]:
    """미리 저장해 둔 courses 테이블에서 키워드와 지역에 맞는 교육 과정을 가져옵니다."""
    if supabase is None:
        return []
    try:
        query = supabase.table("courses").select("*")
        
        # 키워드 필터링
        if subject and subject != "재취업 일반":
            query = query.or_(f"title.ilike.%{subject}%,institution.ilike.%{subject}%")
            
        # 지역 필터링
        if location and location not in ("서울", "경기", "전국"):
            loc_clean = location.replace("서울 ", "").replace("경기 ", "").strip()
            query = query.ilike("location", f"%{loc_clean}%")
            
        result = query.limit(limit).execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"[DB Course Search Error] {e}")
        return []
