from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import AgentState
import nodes

def route_intent(state: AgentState) -> str:
    """
    사용자의 '의도(intent)'를 보고 다음에 어떤 기능 노드로 보낼지 결정하는 길잡이 함수(라우터)입니다.
    - state 안에 저장된 'intent' 값을 읽어와 미리 약속된 다음 노드(기능) 이름으로 안내합니다.
    """
    intent = state.get("intent", "basic_chat")
    
    # 챗봇이 지원하는 핵심 기능 노드들의 이름 목록입니다.
    routes = [
        "resume_gen",       # 자기소개서 작성 및 온보딩 질문
        "resume_verify",    # 자소서 유튜브 RAG 검증
        "job_search",       # 일자리 검색 및 추천
        "apply_guide",      # 구직/면접 가이드북
        "basic_chat"        # 일반 인사 및 대화 (기본 대기실)
    ]
    
    # 분석된 의도가 목록에 있으면 해당 기능 노드로 연결하고, 없으면 기본 일상대화(basic_chat)로 보냅니다.
    if intent in routes:
        return intent
    return "basic_chat"

# 1. 챗봇 대화 흐름을 그릴 도화지(StateGraph)를 준비합니다.
# 이때 대화 내내 들고 다닐 기억 창고인 'AgentState' 규격을 사용합니다.
workflow = StateGraph(AgentState)

# 2. 챗봇을 구성하는 각 방(기능 노드)들을 등록합니다.
# - 'analyze_intent': 사용자 말을 듣고 무엇을 원하는지 분석하는 의도 분석실
workflow.add_node("analyze_intent", nodes.analyze_intent)

# - 각 기능별 전문 상담방들 등록
workflow.add_node("resume_gen", nodes.resume_gen)         # 자소서 작성 및 질문 수집방
workflow.add_node("resume_verify", nodes.resume_verify)   # 유튜브 팁 기반 자소서 검증방
workflow.add_node("job_search", nodes.job_search)         # 맞춤형 일자리 찾기방

workflow.add_node("apply_guide", nodes.apply_guide)       # 면접 팁 등 가이드북 제공방
workflow.add_node("basic_chat", nodes.basic_chat)         # 일상 대화 및 안내 안내방

# 3. 대화의 시작 지점과 이동 규칙(엣지)을 연결합니다.
# - 챗봇방에 들어오면 가장 먼저 'analyze_intent(의도 분석실)'을 거치도록 설정합니다.
workflow.set_entry_point("analyze_intent")

# - 의도 분석(analyze_intent)이 끝난 후에는 'route_intent' 판단에 따라 알맞은 상담방으로 이동시킵니다.
workflow.add_conditional_edges(
    "analyze_intent",
    route_intent
)

# - 각 전문 상담방에서 응답 처리가 끝나면, 대화의 한 턴을 종료(END) 처리하고 유저에게 메시지를 보냅니다.
workflow.add_edge("resume_gen", END)
workflow.add_edge("resume_verify", END)
workflow.add_edge("job_search", END)
workflow.add_edge("apply_guide", END)
workflow.add_edge("basic_chat", END)

# 4. 대화 기록을 기억할 메모리 장치(체크포인터)를 활성화합니다.
# 카카오톡 유저마다 고유한 아이디(thread_id)를 기준으로 대화 기억과 온보딩 단계를 유지해 줍니다.
memory = MemorySaver()

# 5. 모든 노드와 엣지(흐름 규칙)가 그려진 최종 챗봇 앱 그래프를 컴파일하여 완성합니다.
app_graph = workflow.compile(checkpointer=memory)
