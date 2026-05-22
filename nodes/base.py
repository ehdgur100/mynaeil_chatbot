from enum import Enum
import config

class IntentEnum(str, Enum):
    resume_gen = "resume_gen"      # 자소서 생성 및 온보딩
    resume_verify = "resume_verify"  # [파트 2] 자소서 RAG 검증
    job_search = "job_search"      # 일자리 추천
    apply_guide = "apply_guide"    # 상세 지원 가이드
    basic_chat = "basic_chat"

# ========================================================
# ⚙️ Multi-LLM 팩토리 초기화 (Gemini 및 OpenAI 조합)
# ========================================================

# API 키가 환경 변수나 .env에 없을 경우, 임포트 시점 검증 에러를 방지하기 위해 더미 키를 기본값으로 제공합니다.
# 실제 실행(API 호출) 시에는 올바른 키가 필요합니다.
openai_api_key = config.OPENAI_API_KEY or "dummy_openai_key_for_import_check"
gemini_api_key = config.GEMINI_API_KEY or "dummy_gemini_key_for_import_check"

# 1. 빠르고 저렴한 경량 모델 (의도 분류, 일반 대화, 간단한 질답에 사용)
if config.ACTIVE_LLM == "gemini":
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm_fast = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite", 
        google_api_key=gemini_api_key
    )
else:
    from langchain_openai import ChatOpenAI
    llm_fast = ChatOpenAI(
        model="gpt-4o-mini", 
        api_key=openai_api_key
    )

# 2. 논리 연산 및 작문 능력이 높은 고급 고성능 모델 (자소서 작성, RAG 자소서 검증, 가이드 생성에 사용)
# 가급적 GPT-4o나 Gemini Pro 레벨을 사용하도록 고안합니다.
if config.ACTIVE_LLM == "gemini":
    from langchain_google_genai import ChatGoogleGenerativeAI
    # 3.1 flash는 가성비와 스마트함을 겸비한 고급 모델로 사용 가능
    llm_smart = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite", 
        google_api_key=gemini_api_key
    )
else:
    from langchain_openai import ChatOpenAI
    llm_smart = ChatOpenAI(
        model="gpt-4o", 
        api_key=openai_api_key
    )

def get_content(response) -> str:
    """
    AIMessage 등 모델 응답 객체로부터 텍스트 content를 안전하게 문자열로 변환하여 반환합니다.
    (간혹 리스트 형식으로 값이 들어와 발생하는 AttributeError: 'list' object has no attribute 'strip' 등의 버그를 원천 방지)
    """
    if response is None:
        return ""
    # response 객체에 content 속성이 있는지 검사 후 값 획득
    content = getattr(response, "content", response)
    
    if isinstance(content, list):
        # langchain list content 구조를 텍스트로 병합
        return "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content]).strip()
    return str(content).strip()

