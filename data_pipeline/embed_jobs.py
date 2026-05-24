import sys
import os
import time

# config와 database 모듈 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database import supabase, embeddings

def get_text_for_jobs(row):
    """
    워크넷(jobs) 테이블 텍스트 어댑터
    - content 안에 지역, 급여가 모두 합쳐져 있으므로 그대로 씀
    """
    company = row.get("company", "")
    title = row.get("title", "")
    content = row.get("content", "")
    return f"[{company}] {title}\n상세정보:\n{content}"

def get_text_for_jobs3(row):
    """
    서울시(jobs3) 테이블 텍스트 어댑터
    - 지역, 급여, 고용형태 컬럼이 분리되어 있음
    """
    company = row.get("company", "")
    title = row.get("title", "")
    location = row.get("location", "")
    emp_type = row.get("employment_type", "")
    career = row.get("career_required", "")
    salary = row.get("salary", "")
    content = row.get("content", "")

    text = f"[{company}] {title}\n"
    if location: text += f"근무지역: {location}\n"
    if emp_type: text += f"고용형태: {emp_type}\n"
    if career: text += f"경력조건: {career}\n"
    if salary: text += f"급여조건: {salary}\n"
    text += f"상세내용: {content}"
    return text

def get_text_for_job_seoul_50(row):
    """
    job_seoul_50 테이블 텍스트 어댑터
    - 컬럼명이 완전히 다름
    """
    company = row.get("company_or_org", "")
    title = row.get("title", "")
    location = row.get("event_location", "")
    emp_type = row.get("work_condition_name", "")
    career = row.get("career_name", "")
    salary = row.get("pay_text", "")
    content = row.get("raw_data", "")

    text = f"[{company}] {title}\n"
    if location: text += f"근무지역: {location}\n"
    if emp_type: text += f"고용형태: {emp_type}\n"
    if career: text += f"경력조건: {career}\n"
    if salary: text += f"급여조건: {salary}\n"
    text += f"상세내용: {content}"
    return text

def process_table(table_name):
    print(f"\n[시작] {table_name} 테이블 OpenAI 임베딩 파이프라인 가동...")
    
    # 테이블마다 알맞은 어댑터 함수 매핑
    if table_name == "jobs":
        adapter = get_text_for_jobs
    elif table_name == "jobs3":
        adapter = get_text_for_jobs3
    elif table_name == "job_seoul_50":
        adapter = get_text_for_job_seoul_50
    else:
        print(f"[Error] 알 수 없는 테이블: {table_name}")
        return

    # OpenAI는 Rate Limit이 관대하므로 한 번에 더 많이 처리해도 됨
    batch_size = 100 
    total_processed = 0

    while True:
        try:
            # 1. embedding이 null인 row 조회
            res = supabase.table(table_name).select("*").is_("embedding", "null").limit(batch_size).execute()
        except Exception as e:
            print(f"[Error] 데이터 조회 실패: {e}")
            break

        rows = res.data
        if not rows:
            print(f"[완료] {table_name} 테이블 벡터화 완료! (더 이상 빈 칸이 없습니다)")
            break
            
        print(f"[{table_name}] {len(rows)}건 데이터 변환 중 (OpenAI text-embedding-3-small) ...")
        
        # 2. 어댑터를 이용해 텍스트 추출
        texts_to_embed = [adapter(row) for row in rows]
        
        # 3. OpenAI 임베딩 API 호출 (1536차원)
        try:
            vectors = embeddings.embed_documents(texts_to_embed)
        except Exception as e:
            print(f"[Error] OpenAI API 호출 실패: {e}")
            # API 제한에 걸리면 5초 대기 후 재시도
            time.sleep(5)
            continue
            
        # 4. 생성된 벡터를 Supabase에 업데이트
        for row, vector in zip(rows, vectors):
            try:
                supabase.table(table_name).update({"embedding": vector}).eq("id", row["id"]).execute()
                total_processed += 1
            except Exception as e:
                print(f"[Warning] DB 업데이트 실패 (ID: {row.get('id')}): {e}")
                
        print(f"[OK] {table_name} 누적 {total_processed}건 1536차원 벡터 저장 성공!")
        
        # 무리한 서버 부하 방지용 짧은 휴식
        time.sleep(0.5)

if __name__ == "__main__":
    if not supabase:
        print("[Error] Supabase 클라이언트 연결 실패. config 설정을 확인하세요.")
        sys.exit(1)
        
    print("====================================")
    print(" OpenAI 1536차원 추천 엔진 파이프라인")
    print("====================================")
    
    # 3개의 이기종 테이블을 연속으로 처리합니다
    process_table("jobs")
    process_table("jobs3")
    process_table("job_seoul_50")
    
    print("\n[완료] 모든 테이블의 임베딩 처리가 끝났습니다!")
