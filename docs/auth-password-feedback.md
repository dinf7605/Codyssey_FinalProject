# 회원가입 비밀번호 안내 및 이메일 재설정

## 변경
- 가입/재설정에 공통 비밀번호 조건 표시 및 확인란 추가. 미충족 빨강, 충족 초록 및 텍스트로 구분.
- 비밀번호는 기존 서버 규칙(8~64자/영문/숫자/비영숫자)을 그대로 적용하고 trim하지 않음.
- 이메일 중복: 공급자 email_exists/user_already_exists 또는 identities 빈 배열은 HTTP 409.
- 미인증 계정의 프로필 INSERT 중복(23505)은 같은 user_id의 프로필 존재를 확인했을 때만 중복으로 표시.
- 비밀번호 스키마 오류(422), 공급자의 weak_password, 확인란 불일치, 이메일 형식 오류를 구분.
- 로그인 실패 문구는 이메일/비밀번호 통합 문구 유지. 가입에서 중복 이메일을 알리는 UX 는 09-30 기획서 NFR-SEC-01 에 예외로 반영했다 (기능명세서 FR-JOIN-01 에는 이미 같은 문구가 있음). 로그인·비밀번호 재설정은 계정 존재 여부 비노출 유지.
- /forgot-password 이메일 입력 → /auth/forgot-password → Supabase 메일 → /reset-password → /auth/reset-password.
- 메일 발송 장애/과다 요청은 실패로 안내. 없는 이메일인지는 재설정 응답에 표시하지 않음.
- 새 비밀번호 화면은 메일의 type=recovery 및 두 토큰을 확인하고 URL을 즉시 정리함. 토큰은 메모리에만 유지하며 서버가 세션을 검증. 새로고침하면 메일 링크를 다시 열어야 함.
- 기존 동의창, 선택 동의 상태, 목표 탐색 유지 및 안전한 next 경로 처리 보존.
- DB 구조·의존성 목록·환경 파일은 변경하지 않음. Google 로그인은 이번 작업 범위에 없음.

## 메일 연결에 필요한 설정 — 자동 변경하지 않음

1. FastAPI가 실행되는 환경에 PASSWORD_RESET_REDIRECT_URL 설정:
   - 로컬: http://localhost:3000/reset-password
   - 운영: 실제 Vercel 서비스 주소 뒤에 /reset-password 를 붙인 HTTPS 주소.
   - 프론트의 NEXT_PUBLIC_* 변수가 아닌 서버 환경변수다. 프론트만 Vercel에 있으면 프론트 설정만으로 서버에 전달되지 않는다. 서버를 실행하는 담당자가 해당 실행 환경에 설정한다.
   - 기존 config.py가 .env를 우선 읽으므로 실제 읽는 .env와 실행환경 설정을 일치시킨 뒤 서버 재시작.
   - 서버는 요청자가 제공한 redirect 주소, Origin/Host를 사용하지 않는다.
2. 공용 Supabase 담당자가 Authentication → URL Configuration → Redirect URLs에 위 주소를 정확히 등록한다. 운영은 고정한 서비스 주소를 쓰고 불필요한 와일드카드는 피한다.
3. Recovery 메일 템플릿이 기본 ConfirmationURL을 사용하며 지정한 redirect가 적용되는지 확인. SiteURL만으로 링크를 만들던 사용자 지정 템플릿은 담당자가 점검한다.
4. 현재 db.py의 기본 implicit 인증 흐름을 사용한다. PKCE(code 쿼리)나 별도 token_hash 템플릿으로 바꾸면 추가 callback 구현이 필요하다.
5. 기본 메일 서비스의 수신자/발송량 제한, 실제 서비스용 SMTP 설정 여부 확인. 코드는 메일 서비스를 새로 계약하거나 설정하지 않는다.
6. 재설정 URL은 /signup처럼 비로그인 접근 가능해야 한다. 프로젝트의 별도 middleware/proxy/인증 가드가 있다면 /forgot-password 및 /reset-password도 공개 경로에 포함하고 공용 페이지의 토큰 자동 리다이렉트와 충돌하지 않는지 확인한다.

## 검증

프로젝트 루트 PowerShell:
```powershell
Push-Location backend
python -m pytest -q
Pop-Location
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
```

이번에 추가한 test_auth_password_feedback.py는 32개 사례를 검증한다. 공급자와 DB는 mock이다.
기존 전체 테스트는 사용자 프로젝트에서 실행해야 한다. 기존 테스트가 중복 가입도 일반 400으로 반환하도록 고정했다면 새 409 계약과 충돌한다. 실패를 숨기거나 테스트를 삭제하지 말고 해당 기대값과 목적을 검토해 갱신한다.

수동 화면 확인:
- a → a1 → a1! → a1!bcdef 순서로 각 조건 충족 표시 확인. 비밀번호 원문은 표시/로그하지 않음.
- 확인란 일치/불일치, 확인 후 원래 비밀번호를 바꿨을 때 즉시 불일치 전환.
- 필수 동의만 체크하고 선택 미동의로 가입할 수 있는 기존 흐름 확인.
- 기존 이메일 가입 시 중복 안내. 비밀번호 오류와 구분되는지 확인.
- 로그인 화면의 재설정 링크, 이메일 형식 확인, 요청 중 중복 클릭 방지.
- 실제 사용자가 관리하는 테스트 계정으로 메일 수신 → 링크 → 변경 → 새 비밀번호 로그인/기존 비밀번호 로그인 실패 확인.
- 링크 없이 /reset-password 방문, 만료 링크, 기존과 같은 비밀번호, 공급자 일시 장애를 확인.
- 메일 링크/토큰/비밀번호는 캡처하거나 팀 채팅에 공유하지 않음.

## 공식 동작 참고
https://supabase.com/docs/reference/python/auth-resetpasswordforemail
https://supabase.com/docs/reference/python/auth-signup
https://supabase.com/docs/guides/auth/debugging/error-codes
https://supabase.com/docs/guides/auth/redirect-urls
https://supabase.com/docs/guides/auth/passwords
