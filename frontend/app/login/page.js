import Link from 'next/link';

// FR-AUTH-01 이메일 로그인 / FR-AUTH-02 구글 로그인 / FR-AUTH-03 비밀번호 재설정
// 실패 문구는 '아이디 또는 비밀번호가 올바르지 않습니다'로 통일한다 (NFR-SEC-01).
// 비밀번호 조합 규칙은 이 화면에 노출하지 않는다 — 정책 힌트가 된다.

export default function LoginPage() {
  return (
    <main className="shell page">
      <header style={{ paddingTop: 'var(--gap-5)' }}>
        <h1 style={{ fontSize: 22 }}>로그인</h1>
        <p className="muted tiny" style={{ marginTop: 6 }}>
          학습 일정과 진도를 이어서 관리합니다
        </p>
      </header>

      <form className="stack" style={{ gap: 'var(--gap-4)' }}>
        <div className="field">
          <label htmlFor="email">이메일</label>
          <input id="email" name="email" type="email" className="input" autoComplete="email" placeholder="you@example.com" />
        </div>

        <div className="field">
          <label htmlFor="password">비밀번호</label>
          <input id="password" name="password" type="password" className="input" autoComplete="current-password" />
        </div>

        <button type="submit" className="btn btn-primary">로그인</button>
        <button type="button" className="btn">구글 계정으로 계속하기</button>

        <p className="hint" style={{ textAlign: 'center' }}>
          캘린더 접근 권한은 로그인 단계에서 요구하지 않습니다
        </p>
      </form>

      <div style={{ display: 'flex', justifyContent: 'center', gap: 'var(--gap-4)', fontSize: 13 }}>
        <Link href="/signup" className="accent-text">회원가입</Link>
        <span className="muted">비밀번호 재설정</span>
      </div>
    </main>
  );
}
