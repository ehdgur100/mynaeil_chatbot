# 나의내일 챗봇

카카오톡 스킬 서버로 동작하는 중장년 일자리·교육 추천 챗봇입니다. 자기소개서 작성, 일자리 검색, 교육 추천, 교육 신청 준비 가이드를 제공합니다.

## 서버 주소

- 로컬 서버: `http://127.0.0.1:8000`
- 카카오 스킬 URL: `https://aviation-scroll-jovial.ngrok-free.dev/api/chat`
- API 헬스 체크: `GET /`
- 카카오 챗봇 엔드포인트: `POST /api/chat`
- 일자리 추천 엔드포인트: `POST /api/recommend`

## 주요 기능

- 첫 화면 빠른 답장: `📝 자기소개서 작성`, `💼 일자리 검색`, `🎓 교육 추천`
- 교육 추천은 Supabase `education` 테이블 하나에서 조회합니다.
- 교육 종류는 `category` 컬럼으로 구분합니다.
  - `취업훈련`
  - `AI디지털교육`
  - `50플러스센터교육`
- 교육 모집 상태는 `recruitment_status` 컬럼을 사용합니다.
  - 현재 추천 대상: `모집중`, `모집예정`
  - 마감일이 지난 교육과 `모집마감` 교육은 추천에서 제외합니다.
- 교육 추천 후에만 교육 신청 가이드 버튼을 노출합니다.
  - `📋 1번 교육 신청 가이드`
  - `📋 2번 교육 신청 가이드`
  - `📋 3번 교육 신청 가이드`
- 교육 신청 가이드는 `nodes/guide2.py`에서 처리합니다.
- 기존 일자리 지원 가이드는 `nodes/guide.py`에서 유지합니다.

## 추천 기준

교육 추천은 다음 기준으로 정렬합니다.

1. `모집중` 교육 우선
2. `모집중` 교육은 신청마감일이 가까운 순서
3. `모집중` 교육이 부족하면 `모집예정` 교육 포함
4. `모집예정` 교육은 모집시작일이 빠른 순서
5. 사용자의 희망직무, 디지털역량, 거주지역, 질문 키워드와 관련 있는 교육 우선

추천 결과에는 교육명, 카테고리, 모집상태, 장소, 신청마감일 또는 모집시작일, 신청링크, 추천 이유가 포함됩니다.

## 데이터 수집

교육 데이터는 서울시50플러스 사이트에서 수집해 Supabase `education` 테이블에 upsert합니다. 중복 기준은 `application_url`입니다.

- 취업훈련
- AI디지털교육
- 50플러스센터교육
- 모집 상태: `모집중`, `모집예정`
- 임베딩 모델: `text-embedding-3-small`
- 임베딩 차원: `vector(1536)`

일자리 데이터도 매일 갱신합니다.

- Worknet 일자리: `jobs`
- 서울시 일자리: `jobs3`
- 서울시50플러스 일자리: `job_seoul_50`

## 자동 갱신

Windows 작업 스케줄러에 등록된 자동 실행 작업입니다.

- `Mynaeil50plusEducationSync`: 매일 09:00 교육 데이터 수집, 업로드, 임베딩, 지난 마감 데이터 정리
- `MynaeilJobsSync`: 매일 09:30 일자리 데이터 수집, 업로드, 임베딩

수동 실행:

```powershell
.\sync_50plus_education_daily.bat
.\sync_jobs_daily.bat
```

## 실행 방법

가상환경 실행 후 FastAPI 서버를 시작합니다.

```powershell
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

ngrok 주소를 카카오 스킬 URL로 사용할 때는 로컬 서버가 켜져 있어야 합니다.

## 주요 파일

- `main.py`: FastAPI 카카오 스킬 API
- `graph.py`: LangGraph 노드 연결
- `nodes/basic.py`: 첫 화면 메뉴와 기본 대화
- `nodes/intent.py`: 사용자 의도 분석
- `nodes/education.py`: 교육 추천
- `nodes/guide2.py`: 교육 신청·준비 가이드
- `nodes/guide.py`: 일자리 지원 가이드
- `sql/create_education.sql`: Supabase education 테이블 생성 SQL
- `crawl_50plus_education.py`: 취업훈련 수집
- `crawl_50plus_ai_digital.py`: AI디지털교육 수집
- `crawl_50plus_center_education.py`: 50플러스센터교육 수집
- `load_50plus_education_to_supabase.py`: 교육 데이터 Supabase 업로드
- `backfill_education_category.py`: 기존 education 데이터 category/recruitment_status 보정
- `sync_50plus_education_daily.py`: 교육 일일 동기화
- `sync_jobs_daily.py`: 일자리 일일 동기화

## 환경 변수

`.env`에 Supabase와 OpenAI 설정이 필요합니다.

```env
SUPABASE_URL=
SUPABASE_KEY=
OPENAI_API_KEY=
```

## 확인 명령

```powershell
venv\Scripts\python.exe -m py_compile main.py graph.py nodes\__init__.py nodes\basic.py nodes\intent.py nodes\education.py nodes\guide2.py
```

카카오 응답 테스트:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType "application/json" -Body '{"userRequest":{"utterance":"교육 추천","user":{"id":"test-user"}}}'
```
