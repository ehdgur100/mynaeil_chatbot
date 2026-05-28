import sys
import os
import requests
import json
import argparse
from datetime import datetime

# config와 database 모듈의 경로를 찾아서 sys.path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import config
from database.connection import supabase


for proxy_env_name in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(proxy_env_name, None)


def run_seoul_crawler(target_count=3000):
    if not supabase:
        print("[Error] Supabase 클라이언트가 초기화되지 않았습니다.")
        return

    api_key = config.SEOUL_JOB_API_KEY or "4d456c704c6b686a3132304b4f4c7a4c"
    public_base_url = config.PUBLIC_BASE_URL

    start_idx = 1
    chunk_size = 1000  # 한 번에 가져올 개수 (서울시 API 최대 1000)
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
                job_category = row.get("JOBCODE_NM", "")

                # 상세 정보 병합 (내용)
                job_desc = row.get("DTY_CN", "").strip()
                work_time = row.get("WORK_TIME_NM", "").strip()
                deadline = row.get("RCEPT_CLOS_NM", "").strip()
                recruit_count = row.get("RCRIT_NMPR_CO", "")
                education = row.get("ACDMCR_NM", "")
                holiday = row.get("HOLIDAY_NM", "")
                weekly_hours = row.get("WEEK_WORK_HR", "")
                insurance = row.get("JO_FEINSR_SBSCRB_NM", "")
                apply_method = row.get("RCEPT_MTH_NM", "").strip()
                screening = row.get("MODEL_MTH_NM", "").strip()
                papers = row.get("PRESENTN_PAPERS_NM", "").strip()
                manager_org = row.get("MNGR_INSTT_NM", "")
                company_address = row.get("BASS_ADRES_CN", "")
                summary = row.get("GUI_LN", "")

                content_parts = []
                if summary:
                    content_parts.append(f"[요약]\n{summary}")
                if job_category:
                    content_parts.append(f"[모집직종]\n{job_category}")
                if recruit_count:
                    content_parts.append(f"[모집인원]\n{recruit_count}명")
                if job_desc:
                    content_parts.append(f"[담당업무]\n{job_desc}")
                if education or career:
                    content_parts.append(
                        f"[지원자격]\n학력: {education or '관계없음'}\n경력: {career or '관계없음'}"
                    )
                if location:
                    content_parts.append(f"[근무지역]\n{location}")
                if salary:
                    content_parts.append(f"[급여]\n{salary}")
                if emp_type:
                    content_parts.append(f"[고용형태]\n{emp_type}")
                if work_time:
                    content_parts.append(f"[근무시간] {work_time}")
                if holiday or weekly_hours:
                    content_parts.append(
                        f"[근무조건]\n근무형태: {holiday or '확인 필요'}\n주 근로시간: {weekly_hours or '확인 필요'}"
                    )
                if insurance:
                    content_parts.append(f"[사회보험]\n{insurance}")
                if apply_method:
                    content_parts.append(f"[접수방법]\n{apply_method}")
                if screening:
                    content_parts.append(f"[전형방법]\n{screening}")
                if papers:
                    content_parts.append(f"[제출서류]\n{papers}")
                if deadline:
                    content_parts.append(f"[접수마감일] {deadline}")
                if manager_org:
                    content_parts.append(f"[담당기관]\n{manager_org}")
                if company_address:
                    content_parts.append(f"[사업장주소]\n{company_address}")

                full_content = (
                    "\n\n".join(content_parts) if content_parts else "상세 내용 없음"
                )

                full_url = f"{public_base_url}/jobs3/wanted/{job_id}"

                job_data = {
                    "title": title,
                    "company": company,
                    "content": full_content,
                    "url": full_url,
                    "created_at": datetime.now().isoformat(),
                    "external_id": job_id,
                    "location": location,
                    "salary": salary,
                    "career_required": career,
                    "employment_type": emp_type,
                    "job_category": job_category,
                    "deadline": deadline,
                    "apply_method": apply_method,
                    "source": "서울시 일자리 API",
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
    parser = argparse.ArgumentParser(description="Crawl Seoul jobs into Supabase jobs3.")
    parser.add_argument("--target-count", type=int, default=3000)
    args = parser.parse_args()
    run_seoul_crawler(target_count=args.target_count)
