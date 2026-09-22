from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_withdraw_without_confirm():
    # confirm=False면 400 에러가 나야 함
    res = client.request("DELETE", "/settings/withdraw", json={"confirm": False})
    assert res.status_code == 400

def test_withdraw_with_confirm():
    # confirm=True면 성공해야 함
    res = client.request("DELETE", "/settings/withdraw", json={"confirm": True})
    assert res.status_code == 200