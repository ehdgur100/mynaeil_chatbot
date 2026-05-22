import os
from supabase import create_client, Client
import config

supabase: Client = None

try:
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        print("[Database] Supabase 연결 성공")
    else:
        print("[Warning] Supabase URL 또는 Key가 설정되지 않았습니다.")
except Exception as e:
    print(f"[Error] Supabase 연결 실패: {e}")
