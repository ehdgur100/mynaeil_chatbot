from typing import Optional
from database.connection import supabase

def get_user_profile(user_id: str) -> Optional[dict]:
    """사용자의 온보딩 정보를 조회합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    result = supabase.table("users2").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None

def create_user_profile(user_id: str) -> None:
    """새로운 사용자의 온보딩 프로필을 생성합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    supabase.table("users2").insert({"user_id": user_id, "step": 0}).execute()

def save_onboarding_answer(user_id: str, field: str, answer: str, next_step: int) -> None:
    """사용자의 온보딩 답변과 다음 단계를 저장합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    supabase.table("users2").update(
        {field: answer, "step": next_step}
    ).eq("user_id", user_id).execute()

def reset_user_profile(user_id: str) -> None:
    """사용자의 온보딩 상태를 처음부터로 초기화합니다."""
    if supabase is None:
        raise RuntimeError("Supabase가 연결되지 않았습니다.")
    supabase.table("users2").upsert({
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
