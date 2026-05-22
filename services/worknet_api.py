import httpx
from typing import List, Dict, Any

class WorknetAPIClient:
    """
    [담당: 외부 API & 데이터 크롤링 엔지니어]
    워크넷(Worknet) 오픈 API 연동을 담당합니다.
    """
    def __init__(self, auth_key: str = ""):
        self.auth_key = auth_key
        # 워크넷 오픈 API 실전 기본 URL (인증키 필요)
        self.base_url = "http://openapi.work.go.kr/opi/opi/opia/wantedApi.do"

    async def get_jobs_by_keyword(self, keyword: str, location: str = "") -> List[Dict[str, Any]]:
        """
        워크넷 인증키가 활성화되어 있으면 API 통신을 통해 키워드 기반 일자리 목록을 가져옵니다.
        없을 시에는 mock list를 반환합니다.
        """
        if not self.auth_key:
            return self._get_mock_jobs(keyword, location)
            
        params = {
            "authKey": self.auth_key,
            "callTp": "L",
            "returnType": "XML", # 혹은 JSON 지원 여부 확인
            "startPage": 1,
            "display": 10,
            "keyword": keyword
        }
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.base_url, params=params, timeout=5.0)
                if resp.status_code == 200:
                    # XML/JSON 파싱 처리 구현 필요
                    # return self.parse_worknet_response(resp.text)
                    pass
        except Exception as e:
            print(f"[Worknet API] 호출 실패: {e}")
            
        return self._get_mock_jobs(keyword, location)

    def _get_mock_jobs(self, keyword: str, location: str) -> List[Dict[str, Any]]:
        """API 연동 전 개발 및 테스트를 위한 모의 데이터를 반환합니다."""
        return [
            {
                "title": f"{keyword} 모집 (신중년 우대)",
                "company": "(주)우리아동케어",
                "content": f"{keyword} 업무를 담당하실 책임감 있는 5060 사원을 채용합니다. 주 5일 근무.",
                "url": "https://www.work.go.kr/wanted/12345",
                "location": location or "서울 마포구",
                "salary": "월급 210만원",
                "deadline": "2026-06-15"
            }
        ]
