import os
import asyncio
from database import supabase, embeddings
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

# [샘플 데이터] 중장년층 취업 정책 정보
SAMPLE_DATA = [
    {
        "content": "중장년 내일센터: 40세 이상 중장년 구직자에게 생애설계상담, 재취업 지원 서비스, 취업 알선 등을 제공하는 종합 서비스 센터입니다. 전국 주요 도시에 위치해 있습니다.",
        "metadata": {"category": "policy", "source": "고용노동부"}
    },
    {
        "content": "국민내일배움카드: 누구나 신청 가능하며, 훈련비의 45~85%를 지원받아 직업 훈련을 받을 수 있는 카드입니다. 중장년층은 특화 훈련 과정을 통해 디지털 전환 교육 등을 받을 수 있습니다.",
        "metadata": {"category": "edu", "source": "고용노동부"}
    },
    {
        "content": "고령자 고용지원금: 60세 이상 고령자를 일정 수준 이상 고용하는 사업주에게 분기당 30만원씩 지원하여 고령자의 고용 안정을 돕는 제도입니다.",
        "metadata": {"category": "policy", "source": "정부정책"}
    },
    {
        "content": "실업급여 신청 방법: 고용보험 가입자가 비자발적으로 이직한 경우, 워크넷에 구직 등록을 하고 거주지 관할 고용센터를 방문하거나 온라인으로 수급 자격인정 신청을 해야 합니다.",
        "metadata": {"category": "policy", "source": "고용보험"}
    }
]

async def insert_sample_data():
    print("🚀 Supabase에 샘플 데이터를 주입합니다...")
    
    documents = [
        Document(page_content=item["content"], metadata=item["metadata"])
        for item in SAMPLE_DATA
    ]
    
    # SupabaseVectorStore를 통해 데이터 저장
    # 주의: 이 작업을 하기 전 반드시 Supabase SQL Editor에서 테이블 생성 쿼리를 실행해야 합니다!
    try:
        vector_store = SupabaseVectorStore.from_documents(
            documents,
            embeddings,
            client=supabase,
            table_name="documents",
            query_name="match_documents"
        )
        print("✅ 데이터 주입 완료!")
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        print("\n[알림] 혹시 Supabase에서 SQL 쿼리를 아직 실행하지 않으셨나요?")

if __name__ == "__main__":
    asyncio.run(insert_sample_data())
