# 나의내일 챗봇

카카오톡 스킬 서버로 동작하는 중장년 일자리·교육 추천 챗봇입니다. 자기소개서 작성, 일자리 검색, 교육 추천, 일자리 지원 가이드, 교육 신청·준비 가이드를 제공합니다.

## 서버 주소

- 현재 로컬 서버: `http://127.0.0.1:8001`
- 카카오 스킬 URL: `https://aviation-scroll-jovial.ngrok-free.dev/api/chat`
- API 헬스 체크: `GET /`
- 카카오 챗봇 엔드포인트: `POST /api/chat`
- 일자리 추천 엔드포인트: `POST /api/recommend`

ngrok 주소는 로컬 FastAPI 서버가 켜져 있을 때만 정상 동작합니다.

## 주요 기능

- 첫 화면 빠른 답장: `📝 자기소개서 작성`, `💼 일자리 검색`, `🎓 교육 추천`
- 모든 대화 진행 중 `처음으로`, `이전단계` 버튼 제공
- 자기소개서 작성 및 검증
- Supabase 기반 일자리 추천
- Supabase `education` 테이블 기반 교육 추천
- 교육 추천 결과 선택 후 교육 신청·준비 가이드 제공
- 일자리 추천 결과 선택 후 일자리 지원 가이드 제공
- `처음부터`와 `처음으로` 버튼이 동시에 나오지 않도록 빠른답장 중복 제거

## 교육 추천

교육 데이터는 Supabase `education` 테이블 하나에 저장합니다. 테이블을 분리하지 않고 `category` 컬럼으로 교육 종류를 구분합니다.

- `취업훈련`
- `AI디지털교육`
- `50플러스센터교육`

모집 상태는 `recruitment_status` 컬럼을 사용합니다.

- 추천 대상: `모집중`, `모집예정`
- 제외 대상: `모집마감`, 신청마감일이 지난 교육

교육 추천 정렬 기준:

1. `모집중` 교육 우선
2. `모집중` 교육은 신청마감일이 가까운 순서
3. `모집중` 교육이 부족하면 `모집예정` 교육 포함
4. `모집예정` 교육은 모집시작일이 빠른 순서
5. 희망직무, 디지털역량, 거주지역, 질문 키워드와 관련 있는 교육 우선

희망직무 버튼은 분야별 키워드 기준을 적용합니다.

- `생산·제조`
- `돌봄·요양`
- `청소·환경미화`
- `경비·시설관리`
- `배달·운전`
- `사무·행정`

예를 들어 `경비·시설관리`를 선택하면 경비, 보안, 시설관리, 전기설비, 소방, 방재 등과 연결되는 교육만 우선 추천합니다. 관련성이 낮은 교육은 지역이나 모집상태가 맞아도 추천에서 제외합니다.

교육 추천 결과에는 교육명, 카테고리, 모집상태, 장소, 신청마감일 또는 모집시작일, 신청링크, 추천 이유가 포함됩니다.

교육 신청 가이드는 교육 추천 결과가 나온 뒤에만 버튼으로 제공합니다.

- `📋 1번 교육 신청 가이드`
- `📋 2번 교육 신청 가이드`
- `📋 3번 교육 신청 가이드`

교육 신청·준비 가이드 로직은 `nodes/guide2.py`에서 처리합니다. 기존 일자리 지원 가이드는 `nodes/guide.py`에서 유지합니다.

## 일자리 추천

일자리 데이터는 Supabase의 아래 테이블을 사용합니다.

- `jobs`: Worknet 기반 일자리
- `jobs3`: 서울시 일자리 API 기반 일자리
- `job_seoul_50`: 서울시50플러스 일자리

`jobs3`의 상세 링크는 내부 상세 페이지 `/jobs3/wanted/{구인신청번호}`로 연결되며, 서울시 API에서 가져온 상세 내용을 함께 보여줍니다.

일자리 테이블은 임베딩 벡터를 사용해 추천 검색에 활용합니다.

- 임베딩 모델: `text-embedding-3-small`
- 임베딩 차원: `vector(1536)`

지난 마감 일자리 공고는 자동 동기화 과정에서 삭제합니다.

## 데이터 수집

교육 데이터 수집:

- 취업훈련 모집중
- AI디지털교육 모집중
- AI디지털교육 모집예정
- 50플러스센터교육 모집중
- 50플러스센터교육 모집예정

교육 데이터는 `application_url` 기준으로 upsert합니다. 수집 후 Supabase에 업로드하고 임베딩을 생성합니다.

일자리 데이터 수집:

- Worknet 일자리 크롤링/upsert
- 서울시 일자리 API 크롤링/upsert
- 서울시50플러스 일자리 크롤링/upsert
- 지난 마감 공고 삭제
- 새 일자리 임베딩 생성

수집 과정에서는 일부 텍스트 공백 정리, 빈값 정규화, UTF-8 기반 JSON/CSV 저장 처리를 수행합니다. 별도의 독립적인 노이즈 정제 전용 파이프라인은 아니며, 각 크롤러와 업로드 스크립트 안에서 필요한 정규화를 수행합니다.

## 자동 갱신

Windows 작업 스케줄러에 등록된 자동 실행 작업입니다. 현재 두 작업은 `Disabled` 상태입니다.
`Disabled` 상태에서는 매일 09:00이 되어도 크롤링이 자동 실행되지 않으며, 수동 실행 명령을 사용할 때만 동작합니다.

### Mynaeil50plusEducationSync

- 매일 09:00 실행
- 실행 파일: `scripts/sync_education_daily.bat`
- 처리 내용: 교육 데이터 수집, Supabase upsert, 임베딩 생성, 지난 마감 교육 삭제

### MynaeilJobsSync

- 매일 09:00 실행
- 실행 파일: `scripts/sync_jobs_daily.bat`
- 처리 내용: 일자리 데이터 수집, Supabase upsert, 임베딩 생성, 지난 마감 일자리 삭제

작업 스케줄러에서 두 작업을 `사용`으로 바꾸면 다음 실행 시각부터 자동으로 동작합니다.

수동 실행:

```powershell
 .\scripts\sync_education_daily.bat
 .\scripts\sync_jobs_daily.bat
```

## 실행 방법

가상환경의 Python으로 FastAPI 서버를 시작합니다.

```powershell
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8001
```

ngrok을 사용할 때는 로컬 서버 포트와 ngrok 연결 포트가 같아야 합니다.

```powershell
ngrok http --url=aviation-scroll-jovial.ngrok-free.dev 8001
```

## 환경 변수

`.env`에 아래 설정이 필요합니다.

```env
SUPABASE_URL=
SUPABASE_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
WORK24_API_URL=
WORK24_AUTH_KEY=
SEOUL_JOB_API_KEY=
PUBLIC_BASE_URL=https://aviation-scroll-jovial.ngrok-free.dev
```

기본 LLM은 `config.py`에서 `openai`로 설정되어 있습니다.

## 파일 구조

```text
mynaeil_chatbot/
├─ main.py, graph.py, state.py, config.py  # 서버, 대화 그래프, 상태, 환경 설정
├─ nodes/                                  # 챗봇 대화 기능
├─ database/                               # Supabase 연결·조회
├─ data_pipeline/
│  ├─ jobs/                                # 일자리 수집·업로드·임베딩·추천
│  └─ education/                           # 교육 수집·업로드
├─ scripts/
│  ├─ sync_jobs_daily.py/.bat              # 일자리 일괄 실행
│  ├─ sync_education_daily.py/.bat         # 교육 일괄 실행
│  └─ maintenance/                         # 마감 삭제·기존 데이터 보정
├─ sql/                                    # Supabase SQL
├─ data/                                   # 최신 크롤링 CSV·JSON
├─ tests/                                  # 수동 점검과 구조 테스트
└─ tools/ngrok/                            # ngrok 실행 파일
```

## 주요 모듈

### 서버와 그래프

- `main.py`: FastAPI 앱입니다. `/api/chat`, `/api/recommend`, `/jobs3/wanted/{구인신청번호}`를 제공합니다.
- `graph.py`: 사용자 의도에 따라 자기소개서, 일자리, 교육, 가이드 노드를 연결합니다.
- `state.py`: LangGraph에서 공유하는 상태 구조를 정의합니다.
- `config.py`: `.env`를 루트 기준으로 불러오고 Supabase, OpenAI, Gemini, Work24, 서울시 API 설정을 관리합니다.
- `ssl_patch.py`: Gemini API 등 외부 LLM 호출 시 발생하는 SSL 인증서 관련 오류를 certifi 기반으로 해결하는 패치 모듈입니다.

### 챗봇 노드

- `nodes/basic.py`: 첫 화면 메뉴와 기본 응답을 처리합니다.
- `nodes/intent.py`: 사용자 발화의 의도를 분석합니다.
- `nodes/navigation.py`: `처음으로`, `이전단계` 버튼을 붙이고 `처음부터`/`처음으로` 중복을 제거합니다.
- `nodes/onboarding.py`: 자기소개서 작성 흐름을 처리합니다.
- `nodes/resume.py`: 자기소개서 생성 로직을 처리합니다.
- `nodes/resume_verify.py`: 자기소개서 검증과 첨삭을 처리합니다.
- `nodes/job.py`: 일자리 검색과 추천 흐름을 처리합니다.
- `nodes/education.py`: 교육 추천, 모집상태 필터, 직무별 키워드 매칭을 처리합니다.
- `nodes/guide.py`: 일자리 지원 가이드를 처리합니다.
- `nodes/guide2.py`: 교육 신청·준비 가이드를 처리합니다.
- `nodes/policy.py`: 정책 관련 응답을 처리합니다.
- `nodes/base.py`: 공통 LLM, 메시지 처리, 의도 enum을 정의합니다.

### 데이터베이스

- `database/connection.py`: Supabase 클라이언트를 생성합니다.
- `database/operations.py`: 사용자 프로필, 자기소개서 상태, DB 작업을 처리합니다.
- `database/vector_search.py`: 벡터 기반 검색을 처리합니다.

### 일자리 파이프라인

- `data_pipeline/jobs/`: Worknet·서울시·50플러스 일자리 수집, `jobs`·`jobs3`·`job_seoul_50` 업로드, 임베딩과 추천 기능입니다.
- `scripts/sync_jobs_daily.py`: 일자리 전체 수집과 정리 작업의 실행 진입점입니다.

### 교육 파이프라인

- `data_pipeline/education/`: 취업훈련, AI디지털교육, 50플러스센터교육 수집과 `education` 테이블 업로드 기능입니다.
- `scripts/sync_education_daily.py`: 교육 전체 수집과 정리 작업의 실행 진입점입니다.
- `scripts/maintenance/`: 마감 공고 삭제와 기존 데이터 보정 작업입니다.

### SQL과 데이터

- `sql/create_education.sql`: Supabase `education` 테이블, 인덱스, 벡터 컬럼 생성 SQL입니다.
- `sql/create_job_seoul_50.sql`: Supabase `job_seoul_50` 테이블, 인덱스, 벡터 컬럼 생성 SQL입니다.
- `sql/match_jobs_hybrid.sql`: 일자리 하이브리드 검색 함수 SQL입니다.
- `data/50plus_education_applying/`: 취업훈련 모집중 수집 결과입니다.
- `data/50plus_ai_digital_joining/`: AI디지털교육 모집중 수집 결과입니다.
- `data/50plus_ai_digital_pending/`: AI디지털교육 모집예정 수집 결과입니다.
- `data/50plus_center_education_joining/`: 50플러스센터교육 모집중 수집 결과입니다.
- `data/50plus_center_education_pending/`: 50플러스센터교육 모집예정 수집 결과입니다.
- `data/50plus_private_applying/`: 서울시50플러스 일자리 수집 결과입니다.
- `backups/`, `staging/`: 로컬 백업·검증 폴더이며 Git 커밋에서 제외됩니다.

## 확인 명령

문법 확인:

```powershell
venv\Scripts\python.exe -m py_compile main.py graph.py nodes\__init__.py nodes\basic.py nodes\intent.py nodes\education.py nodes\guide2.py
```

카카오 응답 테스트:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/chat -ContentType "application/json; charset=utf-8" -Body '{"userRequest":{"utterance":"교육 추천","user":{"id":"test-user"}}}'
```

일자리 자동 동기화 테스트:

```powershell
venv\Scripts\python.exe scripts\sync_jobs_daily.py --skip-embeddings
```

교육 자동 동기화 테스트:

```powershell
venv\Scripts\python.exe scripts\sync_education_daily.py --skip-embeddings
```


[나의내일 AI 챗봇 프로젝트 최종본.pptx](https://github.com/user-attachments/files/28454951/AI.pptx)
