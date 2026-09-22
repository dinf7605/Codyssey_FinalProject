import os
from supabase import create_client, Client
from dotenv import load_dotenv

# 1) .env 파일에서 환경변수 불러오기
load_dotenv()

# 2) 환경변수에서 URL과 키 읽기
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")

# 3) 값이 없으면 에러로 알려주기 (실수 방지!)
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("환경변수 SUPABASE_URL 또는 SUPABASE_SECRET_KEY가 없어요!")

# 4) Supabase 클라이언트 생성
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 연결 테스트
if __name__ == "__main__":
    response = supabase.table("users").select("*").execute()
    print("연결 성공! 📊 데이터:", response.data)