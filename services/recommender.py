import numpy as np
from typing import List, Dict, Any

def content_based_filtering(user_profile: Dict[str, Any], jobs: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """
    사용자의 희망 직무(desired_job), 보유 경력(career), 강점(strengths) 키워드와 
    공고(jobs)의 제목 및 본문 텍스트 간 유사도를 계산해 매칭하는 콘텐츠 기반 필터링 알고리즘.
    
    [외부 API & 추천 시스템 엔지니어 가이드]
    실무 단계에서는 KoNLPy 형태소 분석 및 TF-IDF 벡터화(scikit-learn) 또는 
    OpenAI text-embedding-3-large 임베딩 벡터 간 코사인 유사도를 활용하도록 고도화하십시오.
    """
    if not user_profile or not jobs:
        return jobs[:top_n]

    # 비교 타겟 문자열 구성
    user_words = []
    for field in ["desired_job", "career", "skills", "strengths"]:
        val = user_profile.get(field)
        if val:
            user_words.extend([w.strip() for w in val.replace(",", " ").split() if w.strip()])

    scored_jobs = []
    for job in jobs:
        # 공고 텍스트 병합 (제목 + 내용 + 카테고리)
        job_text = f"{job.get('title', '')} {job.get('content', '')} {job.get('job_category', '')}"
        
        # 키워드 매칭 스코어 계산
        score = 0.0
        for word in user_words:
            if word in job_text:
                # 희망 직무 매칭 시 가중치 부여
                if word == user_profile.get("desired_job"):
                    score += 5.0
                else:
                    score += 1.0
                    
        # 근무지 매칭 가중치 (구/시 단위 비교)
        user_loc = user_profile.get("location", "")
        job_loc = job.get("location", "")
        if user_loc and job_loc and (user_loc in job_loc or job_loc in user_loc):
            score += 3.0

        scored_jobs.append((job, score))

    # 점수 내림차순 정렬 후 반환
    scored_jobs.sort(key=lambda x: x[1], reverse=True)
    return [item[0] for item in scored_jobs[:top_n]]

def collaborative_filtering(user_id: str, active_users: List[Dict[str, Any]], jobs: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """
    비슷한 경로나 성향을 가진 다른 신중년 유저들의 온보딩 프로필 데이터 유사도를 구하고,
    유사 유저군이 선호하거나 지원했던 일자리 공고를 추천하는 사용자 기반 협업 필터링 알고리즘.
    
    [외부 API & 추천 시스템 엔지니어 가이드]
    실무 단계에서는 유저-아이템 상호작용 매트릭스(User-Item Interaction Matrix)를 구축하고
    SVD(특이값 분해)나 코사인 유사도 행렬곱을 활용하여 정교화하십시오.
    """
    # 뼈대 알고리즘: 유사 프로필을 가진 '이웃 유저(Neighborhood)' 매칭
    target_user = next((u for u in active_users if u.get("user_id") == user_id), None)
    if not target_user or len(active_users) <= 1:
        return jobs[:top_n]

    target_fields = [target_user.get("desired_job"), target_user.get("location")]
    
    user_similarities = []
    for other_user in active_users:
        if other_user.get("user_id") == user_id:
            continue
        
        # 단순 프로필 중복도 스코어 계산
        sim_score = 0
        if other_user.get("desired_job") == target_user.get("desired_job"):
            sim_score += 3
        if other_user.get("location") == target_user.get("location"):
            sim_score += 2
        if other_user.get("work_condition") == target_user.get("work_condition"):
            sim_score += 1
            
        user_similarities.append((other_user, sim_score))

    # 가장 프로필이 유사한 탑 3 유저 선정
    user_similarities.sort(key=lambda x: x[1], reverse=True)
    neighbors = [item[0] for item in user_similarities[:3]]

    # 이웃 유저들이 가질 만한 추천 공고 필터링 (가상 매칭)
    # 실제로는 이웃 유저들이 조회/지원한 공고 매핑 테이블(예: 지원 이력 테이블)을 조인하여 연동합니다.
    recommended_jobs = []
    for neighbor in neighbors:
        for job in jobs:
            # 이웃 유저의 희망직종이 공고 카테고리와 겹치는 경우 추천 대상으로 지정
            if neighbor.get("desired_job") and neighbor.get("desired_job") in job.get("job_category", ""):
                if job not in recommended_jobs:
                    recommended_jobs.append(job)

    if not recommended_jobs:
        return jobs[:top_n]
        
    return recommended_jobs[:top_n]
