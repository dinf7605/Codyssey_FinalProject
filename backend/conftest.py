"""pytest 가 backend/ 를 임포트 경로로 잡게 한다.

이게 없으면 테스트에서 `from schemas.plan import ...` 가 안 된다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
