"""인증 UX 계약 테스트: Supabase/메일 실제 호출 없이 검증한다."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from routers import auth
from schemas.user import SignupRequest, ForgotPasswordRequest, ResetPasswordRequest

class ProviderError(Exception):
    def __init__(self, code=None, status=400):
        super().__init__('internal provider detail must not leak')
        self.code, self.status = code, status

@pytest.fixture
def clients(monkeypatch):
    client, db = Mock(), Mock()
    monkeypatch.setattr(auth, 'new_auth_client', lambda: client)
    monkeypatch.setattr(auth, 'get_supabase_client', lambda: db)
    monkeypatch.setenv('PASSWORD_RESET_REDIRECT_URL', 'https://app.example.com/reset-password')
    client.auth.sign_up.return_value = SimpleNamespace(user=SimpleNamespace(id='test-id', identities=[{}]), session=None)
    return client, db

def signup_request():
    return SignupRequest(email='member@example.com', password='Example123!', nickname='학습자', agree_privacy=True, agree_ai_notice=True, agree_marketing=False)

def assert_http(status, call, text=None):
    with pytest.raises(HTTPException) as raised:
        call()
    assert raised.value.status_code == status
    if text: assert text in raised.value.detail
    assert 'internal provider detail' not in raised.value.detail

@pytest.mark.parametrize('code', ['email_exists', 'user_already_exists'])
def test_provider_duplicate(clients, code):
    client, db = clients
    client.auth.sign_up.side_effect = ProviderError(code)
    assert_http(409, lambda: auth.signup(signup_request()), '이미 가입된')
    db.table.assert_not_called()

def test_obfuscated_duplicate(clients):
    client, db = clients
    client.auth.sign_up.return_value.user.identities = []
    assert_http(409, lambda: auth.signup(signup_request()), '이미 가입된')
    db.table.assert_not_called()

@pytest.mark.parametrize('code,status,text', [('weak_password',400,'비밀번호'), ('over_request_rate_limit',429,'요청'), ('unknown',400,'가입하지')])
def test_signup_errors(clients, code, status, text):
    clients[0].auth.sign_up.side_effect = ProviderError(code)
    assert_http(status, lambda: auth.signup(signup_request()), text)

def test_signup_success_preserves_consents(clients):
    result = auth.signup(signup_request())
    assert result['requires_email_confirmation'] is True
    record = clients[1].table.return_value.insert.call_args.args[0]
    assert record['agree_privacy'] is True and record['agree_marketing'] is False
    assert 'password' not in record

@pytest.mark.parametrize('exists,status', [(True,409),(False,503)])
def test_profile_unique_error_verified_by_user_id(clients, exists, status):
    client, db = clients
    db.table.return_value.insert.return_value.execute.side_effect = ProviderError('23505')
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{'user_id':'test-id'}] if exists else []
    assert_http(status, lambda: auth.signup(signup_request()))
    client.auth.admin.delete_user.assert_not_called()
    db.table.return_value.select.return_value.eq.assert_called_once_with('user_id', 'test-id')

def test_recovery_uses_fixed_redirect(clients):
    assert '가입된 이메일이라면' in auth.forgot_password(ForgotPasswordRequest(email='member@example.com'))['message']
    clients[0].auth.reset_password_for_email.assert_called_once_with('member@example.com', {'redirect_to':'https://app.example.com/reset-password'})

@pytest.mark.parametrize('url', ['', 'https://app.example.com/', 'http://app.example.com/reset-password', 'https://user:pass@app.example.com/reset-password', 'https://app.example.com/reset-password?next=bad', 'https://app.example.com/reset-password#bad', 'https://app.example.com:bad/reset-password'])
def test_bad_recovery_configuration_does_not_send(clients, monkeypatch, url):
    monkeypatch.setenv('PASSWORD_RESET_REDIRECT_URL',url)
    assert_http(503, lambda: auth.forgot_password(ForgotPasswordRequest(email='member@example.com')))
    clients[0].auth.reset_password_for_email.assert_not_called()

def test_local_recovery_configuration(clients, monkeypatch):
    monkeypatch.setenv('PASSWORD_RESET_REDIRECT_URL','http://localhost:3000/reset-password')
    auth.forgot_password(ForgotPasswordRequest(email='member@example.com'))
    assert clients[0].auth.reset_password_for_email.call_args.args[1]['redirect_to'].startswith('http://localhost:3000/')

@pytest.mark.parametrize('code,status', [('over_email_send_rate_limit',429),('unexpected_failure',503)])
def test_mail_failure_not_reported_as_sent(clients, code, status):
    clients[0].auth.reset_password_for_email.side_effect = ProviderError(code)
    assert_http(status, lambda: auth.forgot_password(ForgotPasswordRequest(email='member@example.com')))

def test_unknown_email_same_generic_result(clients):
    clients[0].auth.reset_password_for_email.side_effect = ProviderError('user_not_found')
    assert auth.forgot_password(ForgotPasswordRequest(email='member@example.com')) == {'message':auth.RESET_SENT}

def reset_request():
    return ResetPasswordRequest(access_token='access', refresh_token='refresh', new_password='Changed123!')

def test_expired_session_does_not_change_password(clients):
    clients[0].auth.set_session.side_effect = ProviderError('bad_jwt')
    assert_http(400, lambda: auth.reset_password(reset_request()), '링크')
    clients[0].auth.update_user.assert_not_called()

@pytest.mark.parametrize('code,status,text',[('same_password',400,'기존 비밀번호'),('weak_password',400,'비밀번호'),('over_request_rate_limit',429,'요청')])
def test_change_password_error_feedback(clients,code,status,text):
    clients[0].auth.update_user.side_effect = ProviderError(code)
    assert_http(status,lambda: auth.reset_password(reset_request()),text)

def test_change_password_success(clients):
    assert '변경되었습니다' in auth.reset_password(reset_request())['message']
    clients[0].auth.set_session.assert_called_once_with('access','refresh')
    clients[0].auth.update_user.assert_called_once_with({'password':'Changed123!'})

@pytest.mark.parametrize('password',['short1!','abcdefgh','12345678','Abcdefg1','Abcdefg!','A1!'+'a'*62])
def test_both_schemas_reject_weak_password(password):
    with pytest.raises(ValidationError):
        SignupRequest(**{**signup_request().model_dump(),'password':password})
    with pytest.raises(ValidationError):
        ResetPasswordRequest(access_token='access',refresh_token='refresh',new_password=password)
