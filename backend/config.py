"""환경변수를 한곳에서 읽는다 — DB·Claude 설정은 모두 이 파일을 거친다.

루트의 .env 를 읽는다. override=True 로 .env 가 셸에 이미 있던 값보다 우선한다.
Claude Code 같은 도구는 자기 셸에 ANTHROPIC_BASE_URL=https://api.anthropic.com 을
미리 넣어 두는데, 이 값이 이기면 Codyssey 게이트웨이 대신 Anthropic 으로 가서 401 이 난다.

배포 서버(Railway)에는 .env 파일이 없으므로 대시보드에 넣은 환경변수가 그대로 쓰인다.
"""

from pathlib import Path

from dotenv import load_dotenv

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(ROOT_ENV, override=True)
