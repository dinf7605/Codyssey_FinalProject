import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")    
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# 일반 클라이언트
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 관리자 클라이언트 (Auth 삭제용)
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# 연결 테스트용 (python db.py 로 직접 실행할 때만 작동)
if __name__ == "__main__":
    response = supabase.table("users").select("*").execute()
    print("연결 성공! 📊 데이터:", response.data)