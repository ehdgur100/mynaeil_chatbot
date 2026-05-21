from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import AgentState
import nodes

def route_intent(state: AgentState) -> str:
    """analyze_intent 노드의 의도 분석 결과에 따라 다음 노드로 제어를 넘깁니다."""
    intent = state.get("intent", "basic_chat")
    
    # 지원 가능한 모든 노드 경로 매핑
    routes = [
        "policy_search", 
        "resume_gen", 
        "resume_verify", 
        "job_search", 
        "edu_recommend", 
        "apply_guide", 
        "basic_chat"
    ]
    if intent in routes:
        return intent
    return "basic_chat"

# 1. 상태 그래프 인스턴스 생성
workflow = StateGraph(AgentState)

# 2. 모든 기능별 노드(부서) 등록
workflow.add_node("analyze_intent", nodes.analyze_intent)
workflow.add_node("policy_search", nodes.policy_search)
workflow.add_node("resume_gen", nodes.resume_gen)
workflow.add_node("resume_verify", nodes.resume_verify)
workflow.add_node("job_search", nodes.job_search)
workflow.add_node("edu_recommend", nodes.edu_recommend)
workflow.add_node("apply_guide", nodes.apply_guide)
workflow.add_node("basic_chat", nodes.basic_chat)

# 3. 엣지 및 워크플로우 흐름 설정
# 처음 진입할 때 무조건 analyze_intent 노드를 수행합니다.
workflow.set_entry_point("analyze_intent")

# analyze_intent 노드 수행 후, 분석된 의도에 매칭되는 기능 노드로 라우팅
workflow.add_conditional_edges(
    "analyze_intent",
    route_intent
)

# 각 기능 노드의 작업이 끝나면 워크플로우를 종료(END) 처리
workflow.add_edge("policy_search", END)
workflow.add_edge("resume_gen", END)
workflow.add_edge("resume_verify", END)
workflow.add_edge("job_search", END)
workflow.add_edge("edu_recommend", END)
workflow.add_edge("apply_guide", END)
workflow.add_edge("basic_chat", END)

# 4. 메모리(체크포인터) 영속성 설정
# 카카오톡 유저 고유 세션(thread_id)별 대화 기억 및 온보딩 유지를 가능케 합니다.
memory = MemorySaver()

# 5. 그래프 최종 컴파일
app_graph = workflow.compile(checkpointer=memory)
