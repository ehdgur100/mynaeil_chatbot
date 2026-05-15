import os
from supabase import create_client, Client
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
import config

# Supabase 클라이언트 초기화
try:
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    else:
        supabase = None
        print("[Warning] Supabase URL 또는 Key가 설정되지 않았습니다.")
except Exception as e:
    supabase = None
    print(f"[Error] Supabase 연결 실패: {e}")

# Gemini Embedding 2 Preview (실제 작동 확인, 3072차원)
embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-2-preview",
    google_api_key=config.GEMINI_API_KEY
)

async def search_documents(query: str, k: int = 3) -> list[Document]:
    """
    Supabase RPC를 직접 호출하는 커스텀 벡터 검색 함수.
    langchain-community의 SupabaseVectorStore 버전 충돌 문제를 우회합니다.
    """
    if supabase is None:
        return []
    try:
        # 1. 쿼리를 벡터로 변환
        query_vector = embeddings.embed_query(query)
        
        # 2. Supabase RPC 직접 호출 (최신 SDK 호환)
        result = supabase.rpc(
            "match_documents",
            {
                "query_embedding": query_vector,
                "match_threshold": 0.3,
                "match_count": k
            }
        ).execute()
        
        # 3. LangChain Document 형식으로 변환
        docs = []
        for row in result.data:
            docs.append(Document(
                page_content=row["content"],
                metadata=row.get("metadata", {})
            ))
        return docs
    except Exception as e:
        print(f"[RAG] 검색 실패: {e}")
        return []
