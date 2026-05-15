from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import AgentState
import nodes

def route_intent(state: AgentState) -> str:
    """analyze_intent 노드의 결과에 따라 다음 갈 곳을 결정하는 함수"""
    intent = state.get("intent", "basic_chat")
    
    routes = ["policy_search", "resume_gen", "job_search", "edu_recommend", "basic_chat"]
    if intent in routes:
        return intent
    return "basic_chat"

# 1. 그래프 생성
workflow = StateGraph(AgentState)

# 2. 노드 등록 (부서 배치)
workflow.add_node("analyze_intent", nodes.analyze_intent)
workflow.add_node("policy_search", nodes.policy_search)
workflow.add_node("resume_gen", nodes.resume_gen)
workflow.add_node("job_search", nodes.job_search)
workflow.add_node("edu_recommend", nodes.edu_recommend)
workflow.add_node("basic_chat", nodes.basic_chat)

# 3. 엣지 연결 (흐름 설계)
# 무조건 처음에는 의도 분석 노드로 진입합니다.
workflow.set_entry_point("analyze_intent")

# 의도를 파악한 후에는 조건부로 라우팅합니다.
workflow.add_conditional_edges(
    "analyze_intent",
    route_intent
)

# 전문 노드들의 작업이 끝나면 그래프를 종료합니다.
workflow.add_edge("policy_search", END)
workflow.add_edge("resume_gen", END)
workflow.add_edge("job_search", END)
workflow.add_edge("edu_recommend", END)
workflow.add_edge("basic_chat", END)

# 4. 메모리(세션) 설정
# 이 부분 덕분에 사용자가 중간에 나갔다 와도 과거 대화를 기억할 수 있습니다.
# memory = MemorySaver()

# 5. 그래프 컴파일 (최종 조립)
app_graph = workflow.compile()
