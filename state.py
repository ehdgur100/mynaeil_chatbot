from typing import TypedDict, Annotated, Optional
import operator
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    # LangGraph 표준 메시지 상태 (새 메시지가 올 때마다 리스트에 추가됨)
    messages: Annotated[list[AnyMessage], operator.add]

    # 카카오톡 유저 고유 ID (세션 분리용)
    user_id: str

    # 중장년층 타겟 맞춤형 사용자 정보 상태
    age_group: Optional[str]
    location: Optional[str]
    past_career: Optional[str]

    # 파악된 사용자 의도 (버튼 클릭 등으로 명시적으로 주입될 수도 있음)
    intent: Optional[str]

    # 카카오톡 응답 커스텀 JSON 포맷 저장 (리치 말풍선, 퀵 리플라이 등)
    kakao_response: Optional[dict]

    # 카카오톡 비동기 콜백용 URL
    callback_url: Optional[str]

    # 공고 추천 시 저장되는 최근 추천 목록과 선택한 공고
    last_recommended_jobs: Optional[list[dict]]
    selected_job: Optional[dict]
