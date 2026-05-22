import os
import asyncio
from database.connection import supabase
from database.vector_search import embeddings

# 1. 정부 지원 정책 샘플 데이터
SAMPLE_POLICIES = [
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

# 2. 유튜브 인사담당자 자소서/면접 팁 샘플 데이터
SAMPLE_YOUTUBE_TIPS = [
    {
        "channel_name": "면접왕 이형",
        "script_content": "자기소개서 성장과정이나 직무 경험을 쓸 때는 '열심히 하겠다', '성실하다' 같은 추상적인 표현은 피하십시오. 대신 STAR 기법(상황, 과제, 행동, 결과)을 적용해 '어떤 상황에서 어떤 행동을 해서 수치적으로 무슨 성과를 냈다'로 명확하고 구체적으로 적어야 신뢰감을 줍니다."
    },
    {
        "channel_name": "인사담당자",
        "script_content": "중장년층 구직자들의 가장 큰 무기는 풍부한 실무 경험과 위기 대응력입니다. 자소서 지원동기 부분에는 내가 과거에 어려운 한계 상황을 어떻게 노련한 책임감으로 극복했는지 구체적인 에피소드를 녹여내는 것이 인사담당자들의 눈길을 끄는 비결입니다."
    },
    {
        "channel_name": "면접관 제이",
        "script_content": "입사 후 포부를 작성할 때 단순히 '뼈를 묻겠다'는 식의 무조건적인 충성 맹세는 감점 요인입니다. 그보다는 '나의 과거 직무 경험과 회사의 현재 비즈니스 과제를 매칭하여, 1년 내에 이 직무에서 구체적으로 어떤 기여를 할 것인지' 기여 중심의 구체적 목표를 제시해야 합니다."
    }
]

async def insert_data():
    if supabase is None:
        print("❌ Supabase 연결이 활성화되어 있지 않아 데이터 삽입을 스킵합니다.")
        return

    print("🚀 Supabase 데이터 적재 파이프라인 가동...")

    # ==========================================
    # A. 정부 지원 정책 적재 (documents 테이블)
    # ==========================================
    print("\n[A] 정부 정책 데이터 적재 중...")
    for item in SAMPLE_POLICIES:
        content = item["content"]
        metadata = item["metadata"]
        try:
            # text-embedding-3-large로 임베딩 추출
            vector = await embeddings.aembed_query(content)
            
            # 테이블 직접 insert
            supabase.table("documents").insert({
                "content": content,
                "metadata": metadata,
                "embedding": vector
            }).execute()
            print(f"✅ 적재 완료: {content[:20]}...")
        except Exception as e:
            print(f"❌ 정책 데이터 삽입 실패: {e}")

    # ==========================================
    # B. 유튜브 꿀팁 데이터 적재 (youtube_tips 테이블)
    # ==========================================
    print("\n[B] 유튜브 인사담당자 꿀팁 데이터 적재 중...")
    for item in SAMPLE_YOUTUBE_TIPS:
        channel_name = item["channel_name"]
        script_content = item["script_content"]
        try:
            # 스크립트 본문 임베딩 추출
            vector = await embeddings.aembed_query(script_content)
            
            # 테이블 직접 insert
            supabase.table("youtube_tips").insert({
                "channel_name": channel_name,
                "script_content": script_content,
                "embedding": vector
            }).execute()
            print(f"✅ 적재 완료 ({channel_name}): {script_content[:20]}...")
        except Exception as e:
            print(f"❌ 유튜브 팁 데이터 삽입 실패: {e}")

    print("\n🎉 모든 샘플 데이터 적재 프로세스가 완료되었습니다!")

if __name__ == "__main__":
    asyncio.run(insert_data())
