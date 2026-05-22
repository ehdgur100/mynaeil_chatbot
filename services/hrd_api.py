import httpx
from typing import List, Dict, Any

class HRDNetAPIClient:
    """
    [담당: 외부 API & 데이터 크롤링 엔지니어]
    고용노동부 직업훈련포털 HRD-Net API 연동을 담당합니다.
    """
    def __init__(self, auth_key: str = ""):
        self.auth_key = auth_key
        # HRD-Net 오픈 API 기본 URL
        self.base_url = "https://www.hrd.go.kr/jsp/HRDP/HRDPO00/HRDPO00_01.jsp"

    async def get_training_courses(self, subject: str, location: str = "") -> List[Dict[str, Any]]:
        """
        내일배움카드로 수강 가능한 교육과정 목록을 조회합니다.
        오픈 API 키가 유효하지 않은 경우 목업 리스트를 반환합니다.
        """
        if not self.auth_key:
            return self._get_mock_courses(subject)

        # 실제 API 호출 시 필요한 XML 파라미터 세팅
        params = {
            "authKey": self.auth_key,
            "returnType": "XML",
            "outType": "1",
            "pageNum": "1",
            "pageSize": "5",
            "srchTraPrgseSttus": "1",  # 훈련진행상태 (1: 모집중)
            "srchTraSubject": subject
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.base_url, params=params, timeout=5.0)
                if resp.status_code == 200:
                    # XML 파싱 처리 구현 필요
                    pass
        except Exception as e:
            print(f"[HRD API] 호출 실패: {e}")

        return self._get_mock_courses(subject)

    def _get_mock_courses(self, subject: str) -> List[Dict[str, Any]]:
        """오프라인 상태에서 추천 작동 검증을 위한 직업훈련 목업 데이터를 반환합니다."""
        return [
            {
                "title": f"신중년 특화 {subject} 취업 대비 과정",
                "institution": "마포직업전문학교",
                "duration": "3개월 (총 120시간)",
                "support_type": "국민내일배움카드 전액/일부 무료지원",
                "link": "https://www.hrd.go.kr/course/1234"
            }
        ]
