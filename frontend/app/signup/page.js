import Link from 'next/link';

// FR-JOIN-01 정보 입력 / FR-JOIN-02 개인정보 수집 동의 / FR-JOIN-03 AI 이용 고지
// 필수 동의 2개를 체크해야 가입 버튼이 활성화된다.

export default function SignupPage() {
  return (
    <main className="shell page">
      <header style={{ paddingTop: 'var(--gap-5)' }}>
        <h1 style={{ fontSize: 22 }}>회원가입</h1>
        <p className="muted tiny" style={{ marginTop: 6 }}>
          방금 고른 목표와 가용 시간을 그대로 이어받습니다
        </p>
      </header>

      <form className="stack" style={{ gap: 'var(--gap-4)' }}>
        <div className="field">
          <label htmlFor="su-email">이메일</label>
          <input id="su-email" type="email" className="input" autoComplete="email" />
        </div>

        <div className="field">
          <label htmlFor="su-pw">비밀번호</label>
          <input id="su-pw" type="password" className="input" autoComplete="new-password" />
          <p className="hint">8~64자 · 영문, 숫자, 특수문자를 각각 1자 이상 포함</p>
        </div>

        <div className="field">
          <label htmlFor="su-nick">닉네임</label>
          <input id="su-nick" type="text" className="input" maxLength={10} placeholder="2~10자" />
        </div>

        <fieldset className="card" style={{ padding: 'var(--gap-4)', display: 'flex', flexDirection: 'column', gap: 'var(--gap-3)' }}>
          <legend className="tiny strong" style={{ padding: '0 6px' }}>약관 동의</legend>

          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13 }}>
            <input type="checkbox" style={{ marginTop: 3 }} />
            <span>
              <b>[필수]</b> 개인정보 수집·이용 동의
              <br />
              <span className="dim tiny">
                이메일, 학습 이력, 캘린더 시간대를 수집합니다. 일정 제목과 참석자는 저장하지 않습니다.
              </span>
            </span>
          </label>

          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13 }}>
            <input type="checkbox" style={{ marginTop: 3 }} />
            <span>
              <b>[필수]</b> AI 생성 콘텐츠 고지 확인
              <br />
              <span className="dim tiny">
                추천 목표와 학습 일정은 AI가 생성하며 부정확할 수 있습니다.
              </span>
            </span>
          </label>

          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13 }}>
            <input type="checkbox" style={{ marginTop: 3 }} />
            <span><b className="muted">[선택]</b> 학습 알림 메일 수신</span>
          </label>
        </fieldset>

        <button type="submit" className="btn btn-primary" disabled>
          가입하고 일정 만들기
        </button>
        <p className="hint" style={{ textAlign: 'center' }}>
          필수 항목에 동의하면 버튼이 활성화됩니다
        </p>
      </form>

      <p style={{ textAlign: 'center', fontSize: 13 }}>
        이미 계정이 있나요? <Link href="/login" className="accent-text">로그인</Link>
      </p>
    </main>
  );
}
