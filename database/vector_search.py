import os
import asyncio
from typing import List
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from database.connection import supabase
import config

# 임베딩 차원수는 환경 변수에서 동적으로 읽어옵니다. (OpenAI text-embedding-3-large 기본: 3072차원)
# DB vector 컬럼이 1536차원으로 정의되어 있다면 .env 등에서 EMBEDDING_DIMENSIONS=1536 으로 기입하여 대처 가능합니다.
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "3072"))

openai_api_key = config.OPENAI_API_KEY or "dummy_openai_key_for_import_check"

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-large",
    openai_api_key=openai_api_key,
    dimensions=EMBEDDING_DIMENSIONS
)


async def search_documents(query: str, k: int = 3) -> List[Document]:
    """
    정부 지원 정책 및 문서 데이터베이스를 검색하는 비동기 RAG 함수.
    (FastAPI 이벤트 루프가 동기 네트워크 호출로 블로킹되는 현상을 방지합니다.)
    """
    if supabase is None:
        return []
    try:
        # 1. 비동기로 쿼리 임베딩 벡터 생성
        query_vector = await embeddings.aembed_query(query)
        
        # 2. asyncio.to_thread를 활용하여 동기식 supabase execute()를 별도 스레드로 격리 실행
        result = await asyncio.to_thread(
            lambda: supabase.rpc(
                "match_documents",
                {
                    "query_embedding": query_vector,
                    "match_threshold": 0.3,
                    "match_count": k
                }
            ).execute()
        )
        
        # 3. Document 랩핑 객체 변환
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
    유튜브 인사담당자 면접 및 자소서 작성 꿀팁 데이터베이스(youtube_tips)를 검색하는 비동기 RAG 함수.
    
    [RAG & DB 엔지니어 가이드]
    이 함수가 올바르게 작동하려면 Supabase SQL Editor에서 아래와 같은 match_youtube_tips RPC 함수가 등록되어 있어야 합니다:
    
    CREATE OR REPLACE FUNCTION match_youtube_tips (
      query_embedding vector(3072),  -- 차원수에 맞춰 조절
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
        query_vector = await embeddings.aembed_query(query)
        
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
        
        docs = []
        for row in result.data:
            # 자소서 검증 프롬프트가 인사담당자의 이름을 구체적으로 지목할 수 있도록
            # channel_name 정보를 metadata에 함께 넘겨줍니다.
            docs.append(Document(
                page_content=row.get("script_content", ""),
                metadata={"channel_name": row.get("channel_name", "인사담당자")}
            ))
        return docs
    except Exception as e:
        print(f"[RAG] 유튜브 자소서 팁 검색 실패: {e}")
        return []
