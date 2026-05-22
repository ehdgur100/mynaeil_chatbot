from typing import TypedDict, Annotated, Optional
import operator
from langchain_core.messages import AnyMessage

class AgentState(TypedDict):
    """
    챗봇이 대화를 나누는 동안 유저별로 '기억해야 하는 정보'를 모아둔 상태 창고(State)입니다.
    이 구조에 담긴 데이터는 대화 흐름이 진행되는 동안 계속 유지되고 갱신됩니다.
    """
    
    # 1. 대화 내역: 유저와 챗봇이 나눈 모든 메시지 목록입니다.
    # - operator.add 설정 덕분에, 새로운 메시지가 생기면 기존 목록 끝에 차곡차곡 합쳐집니다.
    messages: Annotated[list[AnyMessage], operator.add]
    
    # 2. 유저 고유 식별자: 카카오톡에서 부여한 유저 고유 ID입니다. (세션 및 DB 조회용)
    user_id: str
    
    # 3. 유저 인적/경력 프로필 (필요 시 RAG 추천이나 일자리 매칭 시 활용)
    age_group: Optional[str]      # 나이대 (예: 50대, 60대)
    location: Optional[str]       # 희망 근무 지역 (예: 서울 강서구)
    past_career: Optional[str]    # 과거 경력 (예: 운전직 10년)
    
    # 4. 판단된 대화 의도: 유저가 현재 자소서 작성을 원하는지, 일자리를 찾는지 등의 상태를 기억합니다.
    intent: Optional[str]
    
    # 5. 카카오톡 전송용 데이터: 카카오톡 챗봇 규격에 맞는 말풍선이나 버튼 등의 응답 JSON 데이터가 여기에 담깁니다.
    kakao_response: Optional[dict]
    
    # 6. 비동기 콜백 주소: 답변이 5초 이상 오래 걸릴 때, 카카오톡 서버에 결과를 쏘아줄 주소(Callback URL)를 보관합니다.
    callback_url: Optional[str]
