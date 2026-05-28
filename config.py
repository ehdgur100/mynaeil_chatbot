import os
from dotenv import load_dotenv

# 💡 [수정] config.py 파일이 있는 '진짜 루트 위치'를 기준으로 .env 경로를 강제 지정합니다.
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, ".env")

# 절대 경로를 줘서 어디서 호출하든 무조건 .env를 읽어오도록 만듭니다.
load_dotenv(dotenv_path=env_path)

# 멀티 LLM 환경 변수
# ACTIVE_LLM = os.environ.get("ACTIVE_LLM", "gemini").lower()
ACTIVE_LLM = os.environ.get("ACTIVE_LLM", "openai").lower()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Supabase 설정
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# 고용24 Open API 설정
WORK24_API_URL = os.environ.get("WORK24_API_URL", "")
WORK24_AUTH_KEY = os.environ.get("WORK24_AUTH_KEY", "")
SEOUL_JOB_API_KEY = os.environ.get("SEOUL_JOB_API_KEY", "")
PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL", "https://aviation-scroll-jovial.ngrok-free.dev"
).rstrip("/")
