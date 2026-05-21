import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 멀티 LLM 환경 변수
# ACTIVE_LLM = os.environ.get("ACTIVE_LLM", "gemini").lower()
ACTIVE_LLM = os.environ.get("ACTIVE_LLM", "openai").lower()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Supabase 설정
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# 카카오 채널 메시지 API
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
