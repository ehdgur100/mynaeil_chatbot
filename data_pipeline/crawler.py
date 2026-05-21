import os
import sys
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Windows 터미널 한글 출력 오류 방지
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 상위 폴더 모듈(config, database) import를 위한 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from database import supabase

def crawl_and_insert_jobs_massive(target_count=2000):
    """
    워크넷(Worknet) 채용정보 목록을 대규모로 스크래핑하여
    Supabase jobs 테이블에 적재하는 함수 (Pagination 적용)
    """
    base_url = "https://www.work.go.kr/empInfo/empInfoSrch/list/dtlEmpSrchList.do"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    print(f"🔄 워크넷 채용정보 대규모 크롤링을 시작합니다... (목표: {target_count}건)")
    
    success_count = 0
    page_index = 1
    
    while success_count < target_count:
        # 중장년 우대(pfMatterPreferentialParam=B) 파라미터를 추가하여 중장년층 일자리 위주로 수집
        params = {
            "pageIndex": page_index,
            "pfMatterPreferentialParam": "B"
        }
        
        try:
            res = requests.get(base_url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, 'html.parser')
            job_rows = soup.select('table.board-list tbody tr')
            
            if not job_rows or len(job_rows) == 0:
                print("❌ 더 이상 채용정보를 찾을 수 없거나 차단되었습니다. 크롤링을 조기 종료합니다.")
                break
                
            page_inserted = 0
            
            for row in job_rows:
                if success_count >= target_count:
                    break
                    
                # 회사명 파싱
                cp_el = row.select_one('.cp_name')
                if not cp_el:
                    continue # 빈 줄이나 헤더인 경우 패스
                
                company = cp_el.text.strip()
                
                # 제목 및 공고 링크 파싱
                title_el = row.select_one('.cp-info-in a')
                title = title_el.text.strip() if title_el else "제목 없음"
                
                link_href = title_el.get('href', '') if title_el else ""
                
                if link_href.startswith('/'):
                    full_url = "https://www.work.go.kr" + link_href
                else:
                    full_url = f"https://www.work.go.kr/empInfo/empInfoSrch/list/dtlEmpSrchList.do?title={title}&idx={success_count}"
                # 고용형태, 임금, 근무지 등 상세 정보 파싱
                tds = row.select('td')
                
                content_parts = []
                
                if len(tds) > 3:
                    import re
                    
                    # 1. 담당업무 (자바스크립트 변수 내 숨김 처리된 텍스트 추출)
                    job_desc = ""
                    script_tag = tds[2].select_one('script')
                    if script_tag and script_tag.string:
                        # 지원되는 따옴표(' 또는 ")를 모두 감안한 정규표현식
                        match = re.search(r"var\s+str\s*=\s*['\"](.*?)['\"];", script_tag.string)
                        if match:
                            job_desc = match.group(1).replace('&middot;', '·')
                    
                    if job_desc:
                        content_parts.append(f"[담당업무] {job_desc}")
                        
                    # td2에서 불필요한 script, style 태그 제거하여 텍스트 오염 방지
                    for s in tds[2].select('script, style'):
                        s.extract()
                        
                    # 2. 지원자격 및 지역 (경력, 학력 등)
                    td3_text = " ".join(tds[2].text.split()).replace(title, "").strip()
                    if td3_text: 
                        content_parts.append(f"[지원자격/지역] {td3_text}")
                        
                    # 3. 근무조건 및 임금 (급여, 근무시간, 고용형태 등)
                    td4_text = " ".join(tds[3].text.split()).strip()
                    if td4_text: 
                        content_parts.append(f"[근무조건/임금] {td4_text}")
                        
                    # 4. 등록/마감일
                    if len(tds) > 4:
                        td5_text = " ".join(tds[4].text.split()).strip()
                        if td5_text:
                            content_parts.append(f"[등록/마감일] {td5_text}")
                
                content = "\n".join(content_parts) if content_parts else "상세 내용 없음"
                full_content = f"{content}"
                
                job_data = {
                    "title": title,
                    "company": company,
                    "content": full_content,
                    "url": full_url,
                    "created_at": datetime.now().isoformat()
                }
                
                # Supabase에 적재 (URL 기준 중복 방지)
                try:
                    supabase.table("jobs").upsert(job_data, on_conflict="url").execute()
                    success_count += 1
                    page_inserted += 1
                except Exception as db_err:
                    print(f"⚠️ DB 적재 오류 ({company}): {db_err}")
                    
            print(f"✅ {page_index}페이지 완료: {page_inserted}건 적재 (누적: {success_count}건)")
            
            # 페이지 내 유효한 공고가 없으면 종료
            if page_inserted == 0:
                break
                
            page_index += 1
            
            # 서버 과부하 및 차단 방지를 위한 휴식 시간 (1초)
            time.sleep(1)

        except Exception as e:
            print(f"❌ 크롤링 중 페이지 {page_index}에서 오류 발생: {e}")
            break
            
    print(f"\n🎉 대규모 크롤링 종료! 최종 {success_count}건의 일자리 정보 적재 완료!")

if __name__ == "__main__":
    # 최대 2000건 수집
    crawl_and_insert_jobs_massive(target_count=2000)
