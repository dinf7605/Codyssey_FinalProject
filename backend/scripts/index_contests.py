"""이미 DB에 있는 위비티 공고 제목 최대 20건을 색인한다. 위비티 웹 요청은 하지 않는다.

실행: cd backend && python -m scripts.index_contests
필요: Supabase 설정, OPENAI_API_KEY, migrations/017_contest_title_vectors.sql
"""

from db import get_supabase_client
from services import contest_vector


def main() -> None:
    if not contest_vector.enabled():
        raise SystemExit("OPENAI_API_KEY가 없어 제목 색인을 건너뜁니다")
    saved, failed = contest_vector.index_titles(get_supabase_client())
    print(f"제목 색인 {saved}건 · 실패 {failed}건")


if __name__ == "__main__":
    main()
