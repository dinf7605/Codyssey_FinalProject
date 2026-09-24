"""Claude 공통 호출 규칙 — Codyssey 게이트웨이 형식."""

from services import llm


def test_모델_이름의_날짜는_떼고_보낸다(monkeypatch):
    # 게이트웨이는 날짜 붙은 이름을 "API key is invalid" 로 거절한다
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    monkeypatch.setenv("ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-20250101")

    assert llm.model("main") == "claude-sonnet-4"
    assert llm.model("fast") == "claude-haiku-4"


def test_환경변수가_없으면_기본_모델(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_HAIKU_MODEL", raising=False)

    assert llm.model("main") == llm.MODEL_MAIN
    assert llm.model("fast") == llm.MODEL_FAST


def test_키가_없으면_클라이언트를_만들지_않는다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.get_client() is None


def test_게이트웨이_주소와_재시도_끄기(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-cody-test")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    client = llm.get_client(timeout=7)

    assert str(client.base_url).rstrip("/") == llm.GATEWAY_URL
    assert client.max_retries == 0
