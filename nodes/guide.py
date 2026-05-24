from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import config

_SYSTEM_PROMPT = """당신은 50~60대 신중년 구직자의 취업을 돕는
친절한 취업 도우미입니다.

아래 공고 정보를 바탕으로 지원 방법을 파악하고,
처음 지원하는 분도 따라할 수 있도록
단계별로 안내해주세요.

안내 원칙:
1. 최대한 쉽고 친절하게 설명해주세요.
2. 이메일, 홈페이지, 방문, 전화 중
   어떤 방식인지 먼저 파악하세요.
3. 지원에 필요한 구체적인 정보
   (이메일 주소, URL, 전화번호 등)를
   공고에서 찾아서 포함해주세요.
4. 지원 방법을 파악할 수 없으면
   공고 원문 링크를 안내해주세요.
5. 문장은 짧고 명확하게 써주세요.

출력 형식:
📋 지원 방법 안내

[지원 방식] 이메일/홈페이지/방문/전화 접수

1단계. 내용
2단계. 내용
3단계. 내용
...

📌 공고 원문: (공고 원문 URL)"""

_USER_TEMPLATE = """아래 공고의 지원 방법을 안내해주세요.

[공고 정보]
- 회사명: {company}
- 직무: {title}
- 공고 내용: {description}
- 근무지: {location}
- 마감일: {deadline}
- 공고 원문 URL: {source_url}"""


async def get_apply_guide(job: dict) -> str:
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=config.OPENAI_API_KEY)
    user_prompt = _USER_TEMPLATE.format(
        company=job.get("company") or job.get("company_name") or "정보 없음",
        title=job.get("title") or job.get("job_category") or "정보 없음",
        description=job.get("content") or job.get("description") or "정보 없음",
        location=job.get("location") or "정보 없음",
        deadline=job.get("deadline") or job.get("end_date") or "미정",
        source_url=job.get("source_url") or job.get("url") or "정보 없음",
    )
    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    return response.content


async def apply_guide(_state: dict) -> dict:
    msg = (
        "지원 방법 안내는 일자리 검색 후 공고를 선택하시면\n"
        "단계별로 안내해드려요 😊"
    )
    return {
        "kakao_response": {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": msg}}]},
        }
    }
