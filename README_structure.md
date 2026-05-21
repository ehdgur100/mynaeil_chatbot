# 📂 마이내일(MyNaeil) 챗봇 프로젝트 구조 및 협업 가이드

본 문서는 리팩토링된 LangGraph 기반 챗봇의 폴더 구조와 각 파일의 역할, 그리고 4인 협업 개발 시 효율적으로 업무를 분담하기 위한 가이드를 제공합니다.

---

## 🏗️ 전체 디렉토리 구조 (Folder Structure)

```text
mynaeil_chatbot/
│
├── database/                # 데이터베이스 및 검색 관련 모듈
│   ├── connection.py        # Supabase (PostgreSQL) 연결 및 클라이언트 초기화
│   └── vector_search.py     # pgvector + text-embedding-3-large 기반 RAG 검색
│
├── nodes/                   # LangGraph의 대화 흐름 제어 노드 (비즈니스 로직)
│   ├── base.py              # 공통 LLM (Fast/Smart) 및 LangChain 초기화 (API Key 예외처리 포함)
│   ├── intent.py            # 첫 진입 의도(Intent) 판단 및 온보딩 분기
│   ├── onboarding.py        # 학과/희망직무 등 사용자 데이터 수집 질문 흐름 관리
│   ├── resume.py            # 수집된 데이터를 바탕으로 자기소개서 초안 생성
│   ├── resume_verify.py     # 유튜브 대본 RAG DB를 통한 자소서 내용 팩트체크 및 검증
│   ├── policy.py            # 맞춤형 청년 정책 및 지원금 추천
│   ├── job.py               # 맞춤형 채용 정보 및 일자리 추천
│   ├── training.py          # 직업 훈련 과정 및 교육 정보 추천
│   ├── apply_guide.py       # 취업 지원 가이드 및 면접 팁 안내
│   └── chat.py              # 일상 대화 및 기타 질문 처리 (Fallback)
│
├── services/                # 외부 연동 및 공통 유틸리티 서비스
│   └── kakao.py             # 카카오톡 말풍선, 리스트, 퀵 리플라이 템플릿 생성 헬퍼
│
├── .env                     # 환경 변수 설정 파일 (API Key, DB 접속 정보 등)
├── config.py                # 환경 변수 로드 및 설정값 관리
├── state.py                 # LangGraph 상태 객체(AgentState) 정의
├── graph.py                 # LangGraph 흐름(노드 & 엣지) 정의 및 그래프 빌드
├── main.py                  # FastAPI 웹 서버 엔트리포인트 (카카오톡 웹훅 수신)
├── requirements.txt         # 프로젝트 의존성 라이브러리 목록
└── README_structure.md      # 본 가이드 문서
```

---

## 📄 파일별 세부 역할 설명

### 1. 프로젝트 코어 (Root Files)
*   **[main.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/main.py)**
    *   FastAPI를 구동하고, 카카오톡 챗봇 서버에서 들어오는 `POST /` 요청(웹훅)을 수신합니다.
    *   사용자의 메시지 단위로 LangGraph 인스턴스를 실행하며, 세션별 상태 초기화(상태 누수 방지) 및 카카오톡으로 전달할 최종 응답(JSON)을 변환하여 반환합니다.
*   **[graph.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/graph.py)**
    *   챗봇의 대화 흐름을 결정하는 설계도입니다.
    *   `state.py`의 `AgentState`를 기반으로 하며, 의도 파악(`intent`), 온보딩(`onboarding`), 자소서 작성(`resume`), 정책 추천(`policy`) 등의 모든 노드를 등록하고 연결(Edge)합니다.
*   **[state.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/state.py)**
    *   대화가 이어지는 동안 유지되어야 하는 데이터 구조인 `AgentState`를 정의합니다.
    *   사용자 입력 메시지, 카카오톡 응답 데이터, 대화 흐름 플래그, 사용자 프로필, 자소서 데이터 등이 포함됩니다.
*   **[config.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/config.py)**
    *   `python-dotenv`를 활용하여 `.env` 파일의 API Key들과 DB 정보를 읽어와 코드 전역에서 일관되게 사용할 수 있도록 관리합니다.

---

### 2. 대화 노드 ([nodes/](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes))
각 노드는 독립된 파이썬 함수로 이루어져 있어 담당자별로 코드를 고치기 수월합니다.
*   **[base.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/base.py)**
    *   모든 노드에서 공통으로 쓰는 LLM 모델들을 선언합니다.
    *   `llm_fast` (의도 파악/기본 대화용 GPT-4o-mini 등)와 `llm_smart` (자소서 생성/팩트체크용 GPT-4o 등)를 분리하여 비용과 품질을 최적화합니다.
    *   로컬/테스트 환경에서 API Key가 유실되었을 때 컴파일 오류가 나지 않도록 Dummy Key Fallback 처리가 포함되어 있습니다.
*   **[intent.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/intent.py)**
    *   사용자의 입력을 분석하여 자소서 작성, 정책 조회, 일반 대화 등 어떤 기능으로 보낼지 라우팅 경로를 판단합니다.
    *   기존 유저 정보가 DB에 있는지 확인하여 온보딩을 건너뛰는 역할도 수행합니다.
*   **[onboarding.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/onboarding.py)**
    *   신규 유저의 전공, 관심 분야, 활동 키워드 등 자소서 작성 및 추천에 필요한 최소한의 질문들을 차례로 던지고 수집하는 대화형 온보딩 로직입니다.
*   **[resume.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/resume.py)**
    *   온보딩을 통해 완성된 프로필 데이터를 `llm_smart`에 전달하여, 논리적이고 전문적인 자기소개서 초안을 작성합니다.
*   **[resume_verify.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/resume_verify.py)**
    *   작성된 자기소개서의 내용 중 허위 또는 과장이 없는지, RAG 데이터베이스(유튜브 직무 트렌드 대본 등)를 조회하여 비교 및 피드백(팩트 체크)을 제공합니다.
*   **[policy.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/policy.py)** / **[job.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/job.py)** / **[training.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/training.py)** / **[apply_guide.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/apply_guide.py)**
    *   사용자 상황에 맞는 맞춤 추천 카드를 포맷팅하여 제공하는 정보 전달성 노드들입니다.
*   **[chat.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/nodes/chat.py)**
    *   위의 핵심 시나리오 외에 일상적인 인사나 기타 질문을 LLM을 사용하여 자연스럽게 대답해주는 Fallback 노드입니다.

---

### 3. 데이터베이스 및 유틸리티 ([database/](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/database) & [services/](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/services))
*   **[database/connection.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/database/connection.py)**
    *   Supabase 데이터베이스 인스턴스를 싱글톤 형태로 관리하여 다중 접속 시 안정성을 보장합니다.
*   **[database/vector_search.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/database/vector_search.py)**
    *   `text-embedding-3-large` 임베딩 모델을 사용하여 텍스트 데이터를 벡터화하고, Supabase pgvector에서 유사도가 높은 팩트 데이터(유튜브 대본 정보)를 검색해오는 RAG 핵심 로직입니다.
*   **[services/kakao.py](file:///C:/Users/ehdgu/.gemini/antigravity/worktrees/mynaeil_chatbot/explain-antigravity-refactor/services/kakao.py)**
    *   카카오톡 JSON 응답 규격이 다소 복잡하므로, 단순 텍스트, 카드 리스트, 빠른 답장(Quick Replies) 등을 쉽게 만들 수 있는 유틸리티 함수들을 모아두었습니다.

---

## 👥 4인 개발 협업 역할 분담 가이드

리팩토링된 아키텍처는 파일이 철저히 격리되어 있어, 여러 명이 동시에 작업하더라도 Git 충돌(Merge Conflict)이 일어날 확률이 대폭 낮아집니다. 다음과 같이 역할을 나누어 개발하는 것을 권장합니다.

| 역할 및 담당자 | 주요 작업 파일 | 핵심 작업 내용 |
| :--- | :--- | :--- |
| **A. 아키텍처 & 연동** | `main.py`, `graph.py`, `state.py`, `services/kakao.py` | FastAPI 웹훅 엔드포인트 관리, LangGraph 전체 노드 흐름 설계, 카카오톡 API 공통 템플릿 개발 및 디버깅 |
| **B. 온보딩 & 자소서** | `nodes/intent.py`, `nodes/onboarding.py`, `nodes/resume.py` | 사용자 세션 기반 온보딩 문답 시나리오 고도화, 유저 DB 연동 분기 처리, GPT 프롬프트를 활용한 고품질 자기소개서 초안 생성 로직 개선 |
| **C. RAG & 검색 모델** | `nodes/resume_verify.py`, `database/vector_search.py`, `nodes/chat.py` | 임베딩 성능 튜닝, pgvector RAG 데이터베이스 검색 로직 최적화, 팩트 체크 검증 프롬프트 고도화 및 일상 챗(Fallback) 예외처리 |
| **D. 맞춤형 추천 서비스** | `nodes/policy.py`, `nodes/job.py`, `nodes/training.py`, `nodes/apply_guide.py` | 청년 정책/일자리 채용 정보/직업 교육 추천 프롬프트 세분화, 추천 데이터 결과 매핑 및 퀵리플라이 버튼 연계 작업 |

---

## 🛠️ 로컬 개발 환경 검증 방법

작업 도중 임포트 오류나 문법적 오류가 없는지 터미널에서 아래 명령어를 실행하여 수시로 검증할 수 있습니다.

```bash
# 가상환경 활성화 (Windows)
.\venv\Scripts\activate

# 의존성 라이브러리 검증 및 컴파일 체크
python -c "import main; print('🎉 모든 파일 임포트 및 App 세팅 정상 완료!')"
```
