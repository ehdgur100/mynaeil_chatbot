import sys
import os
import requests
import json
from datetime import datetime

# config와 database 모듈의 경로를 찾아서 sys.path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import config
from database import supabase


def run_seoul_crawler():
    if not supabase:
        print("[Error] Supabase 클라이언트가 초기화되지 않았습니다.")
        return

    # 끝에 불필요하게 중복된 '4'를 제거한 올바른 API Key
    api_key = "4d456c704c6b686a3132304b4f4c7a4c4"[:-1]

    start_idx = 1
    chunk_size = 1000  # 한 번에 가져올 개수 (서울시 API 최대 1000)
    target_count = 3000  # 일단 3천개 정도만 수집해봅시다 (너무 많으면 오래 걸림)
    success_count = 0

    print("서울시 일자리포털 채용정보 API 크롤러 시작...")

    while success_count < target_count:
        end_idx = start_idx + chunk_size - 1
        url = f"http://openapi.seoul.go.kr:8088/{api_key}/json/GetJobInfo/{start_idx}/{end_idx}/"

        try:
            res = requests.get(url, timeout=30)
            data = res.json()

            if "GetJobInfo" not in data:
                print(f"[Error] API 응답 오류: {data}")
                break

            rows = data["GetJobInfo"].get("row", [])
            if not rows:
                print("[Info] 더 이상 가져올 데이터가 없습니다.")
                break

            for row in rows:
                if success_count >= target_count:
                    break

                # 필드 매핑
                job_id = row.get("JO_REQST_NO", "")
                title = row.get("JO_SJ", "제목없음")
                company = row.get("CMPNY_NM", "기업명없음")
                location = row.get("WORK_PARAR_BASS_ADRES_CN", "")
                salary = row.get("HOPE_WAGE", "")
                career = row.get("CAREER_CND_NM", "")
                emp_type = row.get("EMPLYM_STLE_CMMN_MM", "")

                # 상세 정보 병합 (내용)
                job_desc = row.get("DTY_CN", "").strip()
                work_time = row.get("WORK_TIME_NM", "").strip()
                deadline = row.get("RCEPT_CLOS_NM", "").strip()

                content_parts = []
                if job_desc:
                    content_parts.append(f"[담당업무]\n{job_desc}")
                if work_time:
                    content_parts.append(f"[근무시간] {work_time}")
                if deadline:
                    content_parts.append(f"[접수마감일] {deadline}")

                full_content = (
                    "\n\n".join(content_parts) if content_parts else "상세 내용 없음"
                )

                # 서울시 일자리포털 상세 링크 (구인신청번호 활용)
                full_url = f"seoul_job_{job_id}"

                job_data = {
                    "title": title,
                    "company": company,
                    "content": full_content,
                    "url": full_url,
                    "created_at": datetime.now().isoformat(),
                    "location": location,
                    "salary": salary,
                    "career_required": career,
                    "employment_type": emp_type,
                }

                # jobs3 테이블에 upsert
                try:
                    supabase.table("jobs3").upsert(
                        job_data, on_conflict="url"
                    ).execute()
                    success_count += 1
                except Exception as e:
                    print(f"[Warning] DB 저장 실패 ({title}): {e}")

            print(
                f"[OK] {start_idx}~{end_idx}건 적재 완료 (현재 누적: {success_count}건)"
            )
            start_idx = end_idx + 1

        except Exception as e:
            print(f"[Error] API 호출 중 예외 발생: {e}")
            break

    print(f"서울시 일자리포털 데이터 수집 종료! (최종 {success_count}건 적재 완료)")


if __name__ == "__main__":
    run_seoul_crawler()
