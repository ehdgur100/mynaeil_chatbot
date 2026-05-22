import os
import asyncio
from typing import List
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from database.connection import supabase
import config

# 1. OpenAI 임베딩 모델의 차원수를 설정합니다. 
# - text-embedding-3-large 모델은 텍스트를 3072개의 긴 숫자로 된 벡터로 변환합니다.
# - 만약 데이터베이스 테이블의 컬럼이 1536차원 등 다른 크기로 설정되어 있다면 .env에서 변경 가능합니다.
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "3072"))

openai_api_key = config.OPENAI_API_KEY or "dummy_openai_key_for_import_check"

# 2. OpenAI 임베딩 엔진 객체를 준비합니다.
# - 이 엔진은 자연어로 된 문장을 컴퓨터가 이해하고 유사도를 비교할 수 있도록 숫자의 목록(벡터)으로 인코딩해 줍니다.
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-large",
    openai_api_key=openai_api_key,
    dimensions=EMBEDDING_DIMENSIONS
)


async def search_documents(query: str, k: int = 3) -> List[Document]:
    """
    [RAG 정책 검색기]
    사용자의 질문과 가장 어울리는 정부 지원 정책/문서 데이터를 찾아오는 함수입니다.
    - asyncio.to_thread를 사용하여 DB 조회 중 웹 서버 전체가 멈추는(블로킹) 현상을 예방합니다.
    """
    if supabase is None:
        return []
    try:
        # 1) 유저의 검색어(query)를 숫자의 목록(임베딩 벡터)으로 변환합니다.
        query_vector = await embeddings.aembed_query(query)
        
        # 2) Supabase DB 내부에서 실행되는 'match_documents' 데이터베이스 함수(RPC)를 호출해 
        #    유저가 입력한 말과 가장 의미적으로 비슷한 문서 k개를 추천 점수와 함께 조회합니다.
        result = await asyncio.to_thread(
            lambda: supabase.rpc(
                "match_documents",
                {
                    "query_embedding": query_vector,
                    "match_threshold": 0.3,  # 최소 유사도 30% 이상인 데이터만 가져옴
                    "match_count": k
                }
            ).execute()
        )
        
        # 3) 검색된 결과를 LangChain 프레임워크 규격(Document)에 맞춰 알맞게 포장하여 반환합니다.
        docs = []
        for row in result.data:
            docs.append(Document(
                page_content=row.get("content", ""),
                metadata=row.get("metadata", {})
            ))
        return docs
    except Exception as e:
        print(f"[RAG] 정책 검색 실패: {e}")
        return []

async def search_resume_tips(query: str, k: int = 3) -> List[Document]:
    """
    [RAG 유튜브 자소서 팁 검색기]
    유저가 작성한 자기소개서 내용과 가장 어울리는 유튜브 인사담당자들의 피드백 대본을 찾아옵니다.
    
    [참고: DB 엔지니어를 위한 팁]
    이 기능이 작동하려면 Supabase SQL Editor에서 아래 SQL문을 실행해 'match_youtube_tips' 함수를 생성해 두어야 합니다:
    
    CREATE OR REPLACE FUNCTION match_youtube_tips (
      query_embedding vector(3072),
      match_threshold float,
      match_count int
    )
    RETURNS TABLE (
      id bigint,
      channel_name text,
      script_content text,
      similarity float
    )
    LANGUAGE plpgsql
    AS $$
    BEGIN
      RETURN QUERY
      SELECT
        youtube_tips.id,
        youtube_tips.channel_name,
        youtube_tips.script_content,
        1 - (youtube_tips.embedding <=> query_embedding) AS similarity
      FROM youtube_tips
      WHERE 1 - (youtube_tips.embedding <=> query_embedding) > match_threshold
      ORDER BY youtube_tips.embedding <=> query_embedding
      LIMIT match_count;
    END;
    $$;
    """
    if supabase is None:
        return []
    try:
        # 1) 유저의 자소서 문맥을 임베딩 벡터로 변환합니다.
        query_vector = await embeddings.aembed_query(query)
        
        # 2) DB 내의 'match_youtube_tips' 함수를 실행하여 가장 관련도 높은 자소서 피드백 대본을 조회합니다.
        result = await asyncio.to_thread(
            lambda: supabase.rpc(
                "match_youtube_tips",
                {
                    "query_embedding": query_vector,
                    "match_threshold": 0.3,
                    "match_count": k
                }
            ).execute()
        )
        
        # 3) 피드백 작성에 유튜브 채널 이름("[면접왕 이형 팁에 따르면~]")을 언급해 신뢰도를 줄 수 있도록
        #    대본 내용(script_content)과 채널명(channel_name) 정보를 묶어 Document 목록으로 반환합니다.
        docs = []
        for row in result.data:
            docs.append(Document(
                page_content=row.get("script_content", ""),
                metadata={"channel_name": row.get("channel_name", "인사담당자")}
            ))
        return docs
    except Exception as e:
        print(f"[RAG] 유튜브 자소서 팁 검색 실패: {e}")
        return []
