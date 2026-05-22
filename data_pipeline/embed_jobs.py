import sys
import os
import time

# config와 database 모듈 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database import supabase, embeddings

def get_combined_text(row):
    """
    공고 데이터를 자연스러운 형태의 텍스트(Context)로 변환하여 임베딩 품질을 높입니다.
    """
    company = row.get("company", "회사명 없음")
    title = row.get("title", "제목 없음")
    location = row.get("location", "근무지 미상")
    emp_type = row.get("employment_type", "고용형태 미상")
    career = row.get("career_required", "경력무관")
    salary = row.get("salary", "급여 회사내규에 따름")
    content = row.get("content", "")

    # 검색(추천)에 걸리기 좋게 특징을 자연어로 나열
    text = f"[{company}] {title}\n"
    text += f"근무지: {location}\n"
    text += f"고용형태: {emp_type}\n"
    text += f"경력조건: {career}\n"
    text += f"급여: {salary}\n"
    text += f"상세내용: {content}"
    return text

def process_table(table_name):
    print(f"\n {table_name} 테이블 임베딩 파이프라인 시작...")
    batch_size = 50
    total_processed = 0

    while True:
        # embedding이 null인 데이터만 가져오기
        try:
            res = supabase.table(table_name).select("*").is_("embedding", "null").limit(batch_size).execute()
        except Exception as e:
            print(f"[Error] 데이터 조회 실패: {e}")
            break

        rows = res.data
        if not rows:
            print(f"[OK] {table_name} 테이블 임베딩 작업 완료! (모두 채워짐)")
            break
            
        print(f"데이터 {len(rows)}건 임베딩 생성 중...")
        
        # 1. 텍스트 추출
        texts_to_embed = [get_combined_text(row) for row in rows]
        
        # 2. Gemini를 이용한 병렬 임베딩 생성 (Langchain wrapper)
        try:
            vectors = embeddings.embed_documents(texts_to_embed)
        except Exception as e:
            print(f"[Error] Gemini API 임베딩 생성 실패: {e}")
            # Rate limit 등의 문제일 수 있으므로 잠깐 대기 후 재시도
            time.sleep(10)
            continue
            
        # 3. Supabase에 업데이트
        for row, vector in zip(rows, vectors):
            try:
                # 해당 row의 id를 이용해 update 수행
                supabase.table(table_name).update({"embedding": vector}).eq("id", row["id"]).execute()
                total_processed += 1
            except Exception as e:
                print(f"[Warning] DB 업데이트 실패 (ID: {row['id']}): {e}")
                
        print(f"[OK] 누적 {total_processed}건 벡터 변환 및 DB 저장 완료")
        
        # Gemini API Rate Limit 보호를 위해 약간 대기
        time.sleep(1)

if __name__ == "__main__":
    if not supabase:
        print("[Error] Supabase 클라이언트가 설정되지 않았습니다.")
        sys.exit(1)
        
    print("====================================")
    print(" AI 추천을 위한 벡터 임베딩 엔진 가동")
    print("====================================")
    
    process_table("jobs")
    process_table("jobs3")
    
    print("\n 모든 파이프라인 작업이 종료되었습니다!")
