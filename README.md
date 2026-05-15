# 나의내일 (중장년층 재취업 AI 챗봇)

나의내일은 40~60대 중장년층의 재취업을 돕기 위해 정책 정보, 일자리 매칭, 이력서 작성, 교육 추천 등을 제공하는 카카오톡 기반 AI 챗봇입니다.

## 🚀 아키텍처 개요
- **프레임워크**: FastAPI (비동기 콜백 처리)
- **AI/LLM**: LangChain, LangGraph (상태 머신 기반 에이전트 라우팅)
- **모델**: Gemini 3.1 Flash Lite (생성/라우팅), Gemini Embedding 2 Preview (임베딩)
- **Vector DB**: Supabase (PostgreSQL + pgvector)

## 📁 주요 폴더 및 파일 구조

```text
chatbot/
├── main.py         # FastAPI 앱 진입점 및 카카오톡 콜백 라우터
├── graph.py        # LangGraph 상태 머신 및 노드 연결 (워크플로우)
├── nodes.py        # 각 기능별 노드 로직 (의도 분석, 정책 검색, 기본 대화 등)
├── state.py        # LangGraph 에이전트 상태(State) 정의
├── database.py     # Supabase DB 연결 및 커스텀 RAG 검색 로직
├── config.py       # 환경변수 로딩 모듈
├── insert_data.py  # Supabase에 초기 데이터를 주입하는 스크립트
├── requirements.txt# 파이썬 의존성 패키지 목록
└── .env            # (Git 제외) API Key 환경 변수
```

## 🛠️ 팀원 로컬 설정 방법

### 1. 가상환경 생성 및 의존성 설치
```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. 환경변수 설정
프로젝트 루트 폴더에 `.env` 파일을 생성하고 아래 내용을 팀장님께 공유받아 입력하세요.
*(절대 `.env` 파일을 Git에 커밋하지 마세요!)*

```env
# 사용 LLM (gemini 또는 openai)
ACTIVE_LLM=gemini

# Gemini API Key (Google AI Studio)
GEMINI_API_KEY=AIzaSy...

# OpenAI API Key (선택)
OPENAI_API_KEY=sk-proj-...

# Supabase Vector DB 설정
SUPABASE_URL=https://[YOUR_PROJECT].supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsIn...
```

### 3. 서버 및 Ngrok 실행
터미널을 **2개** 열고 각각 실행합니다.

**터미널 1 (FastAPI 서버)**
```bash
uvicorn main:app --reload
```

**터미널 2 (Ngrok)**
```bash
ngrok http 8000
```
> Ngrok에서 발급된 `https://...` 주소를 카카오 i 오픈빌더 스킬 URL에 등록해야 합니다.

## 📌 남은 작업 (TO-DO)
- [ ] **Zero-Typing UI**: 카카오톡 퀵리플라이 및 케로셀 카드 응답 구현
- [ ] **데이터 구축**: 실제 고용노동부/복지부 정책 및 일자리 데이터 Supabase 적재
- [ ] **노드 로직 완성**: `resume_gen`(이력서 작성), `job_search`(일자리 검색), `edu_recommend`(교육 추천) 로직 구체화
