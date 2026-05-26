import os
import sys
import json
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database.connection import supabase
from database.vector_search import embeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# LLM 초기화 (JSON 출력을 강제하여 안정성 확보)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7).bind(
    response_format={"type": "json_object"}
)

prompt_template = PromptTemplate.from_template("""
당신은 중장년층(50대~70대) 취업 준비생 100명의 리얼한 페르소나를 생성하는 전문가입니다.
다양한 직업 배경(사무직 은퇴, 자영업, 현장직, 전업주부 등)을 가진 사람들의 답변을 10명 단위로 생성해 주세요.

반드시 아래 JSON 형식으로 응답해야 합니다. `personas` 배열 안에 10개의 객체를 넣어주세요.

{{
  "personas": [
    {{
      "career": "은행 영업점 창구 업무 25년",
      "skills": "워드프로세서 1급, 금융관련 자격증",
      "desired_job": "사무 보조, 경비 관리직",
      "location": "서울 종로구",
      "work_condition": "주말 제외, 주 3~4일 희망",
      "strengths": "숫자에 밝고 사람들을 친절하게 응대함",
      "goal": "건강을 유지하며 소일거리로 일하고 싶음",
      "proud_experience": "단골 고객이 칭찬 카드를 써줬을 때",
      "hardship": "진상 고객의 무리한 요구를 끝까지 웃으며 해결함"
    }},
    ...
  ]
}}

이번에 생성할 10명의 컨셉: {concept}
""")

chain = prompt_template | llm | StrOutputParser()

concepts = [
    "대기업/중소기업 사무직 은퇴자 그룹 (경비, 관리, 사무보조 희망)",
    "평생 전업주부로 살다가 첫 취업을 준비하는 여성 그룹 (요양보호사, 조리보조 희망)",
    "자영업(식당, 편의점 등) 폐업 후 재취업 희망자 그룹 (배달, 단순노무, 서비스직 희망)",
    "현장직/생산직 출신 은퇴자 그룹 (시설관리, 운전, 물류 희망)",
    "공무원/교사 은퇴자 그룹 (상담, 행정지원, 교육 보조 희망)",
    "건설업/일용직 출신 그룹 (청소, 환경미화, 경비 희망)",
    "영업직 출신 은퇴자 그룹 (매장 관리, 영업 지원 희망)",
    "IT/기술직 출신 은퇴자 그룹 (단순 사무, 전산 보조 희망)",
    "운수업(택시, 버스) 출신 그룹 (마을버스, 배달, 물류 희망)",
    "기타 다양한 경험을 가진 프리랜서/특수고용직 출신 그룹"
]

def format_persona(p):
    return (
        f"[경력] {p.get('career')}\n"
        f"[보유기술/자격] {p.get('skills')}\n"
        f"[희망직무] {p.get('desired_job')}\n"
        f"[희망지역] {p.get('location')}\n"
        f"[근무조건] {p.get('work_condition')}\n"
        f"[나의강점] {p.get('strengths')}\n"
        f"[현재목표] {p.get('goal')}\n"
        f"[뿌듯한경험] {p.get('proud_experience')}\n"
        f"[극복경험] {p.get('hardship')}"
    )

def generate_and_insert():
    print("🚀 중장년 페르소나 100명 생성 및 임베딩 파이프라인 시작...")
    
    total_inserted = 0
    
    for i, concept in enumerate(concepts):
        print(f"\n[{i+1}/10] 컨셉 생성 중: {concept}")
        try:
            # 1. LLM으로 10명 데이터 생성
            result_str = chain.invoke({"concept": concept})
            data = json.loads(result_str)
            personas = data.get("personas", [])
            
            # 2. 텍스트 조립 및 임베딩 변환
            texts_to_embed = []
            for p in personas:
                p["persona_text"] = format_persona(p)
                p["user_id"] = f"fake_user_{total_inserted + len(texts_to_embed) + 1:03d}"
                texts_to_embed.append(p["persona_text"])
                
            print(f"   => {len(personas)}명 텍스트 생성 완료. 임베딩 진행 중...")
            
            # 3. OpenAI 벡터 변환
            vectors = embeddings.embed_documents(texts_to_embed)
            
            # 4. Supabase Insert
            insert_data = []
            for p, vector in zip(personas, vectors):
                insert_data.append({
                    "user_id": p["user_id"],
                    "career": p.get("career", ""),
                    "skills": p.get("skills", ""),
                    "desired_job": p.get("desired_job", ""),
                    "location": p.get("location", ""),
                    "work_condition": p.get("work_condition", ""),
                    "strengths": p.get("strengths", ""),
                    "goal": p.get("goal", ""),
                    "proud_experience": p.get("proud_experience", ""),
                    "hardship": p.get("hardship", ""),
                    "persona_text": p["persona_text"],
                    "embedding": vector
                })
                
            supabase.table("users").insert(insert_data).execute()
            total_inserted += len(insert_data)
            print(f"   ✅ DB 삽입 완료! (누적: {total_inserted}명)")
            
            # API 제한 방지
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            
    print(f"\n🎉 모든 작업 완료! 총 {total_inserted}명의 페르소나가 DB에 저장되었습니다.")

if __name__ == "__main__":
    generate_and_insert()
