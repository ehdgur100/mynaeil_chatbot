import os
import sys

# Windows 환경에서 emoji 출력 시 발생할 수 있는 cp949 인코딩 에러 방지
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import xml.etree.ElementTree as ET
import requests
from datetime import datetime

# 💡 하위 폴더에서 상위 폴더의 모듈을 가져오기 위한 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# 🌟 [수정] 파일 전체를 import 합니다. (클래스가 없기 때문)
import config
from database import supabase


def fetch_and_insert_work24_job(wanted_auth_no: str):
    """
    고용24 상세 채용정보 API를 호출하여 구인 정보를 가져온 후,
    Supabase의 jobs 테이블에 중복 없이 적재(Upsert)하는 함수
    """
    # 🌟 [수정] config.변수명 형태로 직접 접근합니다.
    url = config.WORK24_API_URL
    auth_key = config.WORK24_AUTH_KEY

    if not url or not auth_key:
        print(
            "❌ 에러: .env 또는 config.py에 고용24 API 설정(URL/인증키)이 누락되었습니다."
        )
        return

    # API 요청 파라미터 세팅
    params = {
        "authKey": auth_key,
        "callTp": "D",
        "returnType": "XML",
        "wantedAuthNo": wanted_auth_no,
        "infoSvc": "VALIDATION",
    }

    try:
        print(f"🔄 고용24 채용정보 API 호출 중... (구인번호: {wanted_auth_no})")
        response = requests.get(url, params=params)

        if response.status_code != 200:
            print(f"❌ API 호출 실패 (HTTP Status: {response.status_code})")
            return

        # XML 데이터 파싱
        root = ET.fromstring(response.text)

        # 🌟 API 자체에서 권한/오류 메시지를 반환했는지 먼저 체크합니다
        error_tag = root.find(".//error")
        if error_tag is not None:
            print(f"❌ 고용24 API 오류 발생: {error_tag.text}")
            return

        message_cd = root.find(".//messageCd")
        if message_cd is not None and message_cd.text != "0000":
            message_nm = root.find(".//messageNm")
            msg = message_nm.text if message_nm is not None else "알 수 없는 오류"
            print(f"❌ 고용24 API 응답 오류: [{message_cd.text}] {msg}")
            return

        # 채용정보 관련 핵심 태그 추출
        title_el = root.find(".//wantedTitle")
        corp_el = root.find(".//corpNm")
        job_cont_el = root.find(".//jobCont")
        prefer_el = root.find(".//preferentialCond")

        title = (
            title_el.text.strip()
            if title_el is not None and title_el.text
            else "제목 없음"
        )
        company = (
            corp_el.text.strip()
            if corp_el is not None and corp_el.text
            else "회사명 없음"
        )

        job_contr = (
            job_cont_el.text.strip()
            if job_cont_el is not None and job_cont_el.text
            else "내용 없음"
        )
        prefer_co = (
            prefer_el.text.strip()
            if prefer_el is not None and prefer_el.text
            else "우대사항 없음"
        )
        full_content = f"[직무내용]\n{job_contr}\n\n[우대사항]\n{prefer_co}"

        job_data = {
            "title": title,
            "company": company,
            "content": full_content,
            "url": f"https://www.work24.go.kr/ (구인번호: {wanted_auth_no})",
            "created_at": datetime.now().isoformat(),
        }

        response = supabase.table("jobs").upsert(job_data, on_conflict="url").execute()
        print(f"🎉 Supabase 채용정보 적재 완료: [{company}] {title}")
        return response

    except Exception as e:
        print(f"❌ 고용24 데이터 파이프라인 연동 중 오류 발생: {e}")


if __name__ == "__main__":
    # 🧪 가상환경(venv) 상태에서 실행하여 연동 테스트!
    sample_auth_no = "KJSR002605210001"
    fetch_and_insert_work24_job(sample_auth_no)
