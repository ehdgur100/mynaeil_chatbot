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
PUBLIC_BASE_URL_ENV = os.environ.get("PUBLIC_BASE_URL", "")

def get_ngrok_url() -> str:
    import httpx
    try:
        resp = httpx.get("http://localhost:4040/api/tunnels", timeout=1.0)
        if resp.status_code == 200:
            tunnels = resp.json().get("tunnels", [])
            for t in tunnels:
                public_url = t.get("public_url", "")
                if public_url.startswith("http"):
                    return public_url
    except Exception:
        pass
    return "https://aviation-scroll-jovial.ngrok-free.dev"

if PUBLIC_BASE_URL_ENV:
    PUBLIC_BASE_URL = PUBLIC_BASE_URL_ENV.rstrip("/")
else:
    PUBLIC_BASE_URL = get_ngrok_url().rstrip("/")

def normalize_job_url(url: str) -> str:
    import re
    if not url:
        return ""
    if ".ngrok-free.dev" in url or ".ngrok.io" in url:
        url = re.sub(r"https?://[a-zA-Z0-9.-]+\.ngrok-free\.dev", PUBLIC_BASE_URL, url)
        url = re.sub(r"https?://[a-zA-Z0-9.-]+\.ngrok\.io", PUBLIC_BASE_URL, url)
    return url
