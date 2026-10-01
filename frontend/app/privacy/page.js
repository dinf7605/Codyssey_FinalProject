import Link from 'next/link';

// FR-MAIN-06 개인정보 처리방침 (NFR-PRIV-01/02) — 모든 화면 바닥글(app/layout.js)에서 연결한다.
// 실제로 저장·처리하는 것만 적는다. 기능이 바뀌면 이 문서도 함께 고친다.
//   수집 항목: backend/migrations · 보관: docs/withdrawal-retention.md · AI 처리: backend/services/llm.py

export const metadata = { title: '개인정보 처리방침 — StudyPace' };

const COLLECTED = [
  ['회원가입', '이메일, 닉네임, 비밀번호, 약관 동의 여부와 동의 시각',
    '비밀번호는 인증 서비스(Supabase Auth)가 암호화해 보관하며 StudyPace 는 원문을 저장하지 않습니다.'],
  ['구글 로그인 (선택)', '구글 계정 이메일, 이름', '이름은 닉네임을 미리 채우는 데만 씁니다. 캘린더 권한은 요청하지 않습니다.'],
  ['학습 계획', '목표 이름·기한, 공부 가능 시간(요일·시간대), 학습 단위와 일정 블록, 일정 변경 내역', ''],
  ['학습 기록', '학습 시작·종료 시각과 시간, 블록 완료 여부, 직접 쓴 학습 메모', ''],
  ['학습 메모리', '최근 4주 기록으로 계산한 선호 학습 시간대·예상 대비 실제 시간·완료율, 직접 저장한 관심 분야, 맞지 않다고 평가한 공모전',
    '마이페이지에서 항목별 또는 전체를 바로 지울 수 있습니다.'],
  ['알림', '알림 설정(켜기·시간·방해금지·강도)과 받은 알림 기록', ''],
  ['추천 평가', '목표·공모전 추천에 남긴 평가와 이유', ''],
  ['비회원 이용', '목표 탐색에 입력한 관심 분야·가용 시간, AI 이용 횟수를 세기 위한 임의 식별값',
    '입력값은 이 브라우저 탭에만 30분 보관하고 서버에 저장하지 않습니다.'],
  ['서비스 운영', 'AI 처리 기록(기능 이름, 처리 시간, 사용한 모델, 성공 여부)', '질문·답변 내용은 남기지 않습니다.'],
];

const PROCESSORS = [
  ['Supabase', '회원 인증, 데이터 저장', '회원 정보와 위 학습 데이터 전체'],
  ['Anthropic (Codyssey 교육용 Claude 게이트웨이 경유)', '학습 계획 분해, 목표·공모전 관련성 판단, 일정 변경 요약 문장',
    '목표 이름·기한·가용 시간, 관심 분야, 공모전 제목, 학습 블록 이름. 이메일·닉네임은 보내지 않습니다.'],
  ['Google', '구글 로그인 · 구글 캘린더 바쁜 시간 읽기 (선택한 경우만)', '구글 계정 이메일·이름 / 읽을 기간'],
];

export default function PrivacyPage() {
  return (
    <div className="focus">
      <main className="shell page stack" style={{ gap: 'var(--gap-4)', paddingBottom: 'var(--gap-5)' }}>
        <header className="stack" style={{ gap: 6, paddingTop: 'var(--gap-5)' }}>
          <p className="hint"><Link href="/">← StudyPace</Link></p>
          <h1 style={{ fontSize: 22 }}>개인정보 처리방침</h1>
          <p className="muted tiny">시행일 2026-10-01 · StudyPace 는 코디세이 최종 프로젝트로 만든 비영리 학습 서비스입니다.</p>
        </header>

        <section className="stack" style={{ gap: 8 }}>
          <h2 style={{ fontSize: 16 }}>1. 수집하는 정보</h2>
          <div className="db-scroll" tabIndex={0} aria-label="수집 항목 표">
            <table className="db-table">
              <thead><tr><th scope="col">언제</th><th scope="col">무엇을</th><th scope="col">참고</th></tr></thead>
              <tbody>
                {COLLECTED.map(([when, what, note]) => (
                  <tr key={when}><th scope="row">{when}</th><td>{what}</td><td>{note || '—'}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            구글 캘린더 연동(선택)은 계획을 만들 때 &lsquo;바쁜 시간대&rsquo;(시작·끝)만 한 번 읽습니다. 일정 제목·참석자·장소는 읽을 수 없는 권한이며,
            읽은 바쁜 시간과 구글 권한(토큰)은 서버에 저장하지 않고 읽은 직후 권한을 돌려줍니다. 바쁜 시간은 이 브라우저 탭에 30분만 둡니다.
          </p>
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h2 style={{ fontSize: 16 }}>2. 이용 목적</h2>
          <ul className="stack" style={{ gap: 4, paddingLeft: 18, margin: 0 }}>
            <li>목표에 맞는 학습 계획을 만들고 빈 시간에 배치하며, 밀린 일정을 다시 맞추기 위해</li>
            <li>학습 진도·통계를 보여 주고 화면 구성을 학습량에 맞추기 위해</li>
            <li>학습 시작·미완료·주간 요약 알림을 보내기 위해 (설정에서 끌 수 있습니다)</li>
            <li>목표·공모전을 추천하고, 남긴 평가로 추천을 고치기 위해</li>
            <li>비회원 AI 이용 남용을 막고, 서비스 장애를 확인하기 위해</li>
          </ul>
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h2 style={{ fontSize: 16 }}>3. 처리를 맡기는 곳</h2>
          <div className="db-scroll" tabIndex={0} aria-label="처리 위탁 표">
            <table className="db-table">
              <thead><tr><th scope="col">업체</th><th scope="col">하는 일</th><th scope="col">전달하는 정보</th></tr></thead>
              <tbody>
                {PROCESSORS.map(([who, job, data]) => (
                  <tr key={who}><th scope="row">{who}</th><td>{job}</td><td>{data}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">AI 가 만든 계획·추천은 화면에 AI 표시를 붙여 알리며, 부정확할 수 있습니다.</p>
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h2 style={{ fontSize: 16 }}>4. 보관 기간과 삭제</h2>
          <ul className="stack" style={{ gap: 4, paddingLeft: 18, margin: 0 }}>
            <li><b>회원 탈퇴 시</b> 일정·학습 기록·메모·알림·학습 메모리·추천 평가는 즉시 삭제합니다.</li>
            <li>이메일·닉네임·약관 동의 정보는 분쟁 대응을 위해 별도 보관한 뒤 <b>1년 후 자동 삭제</b>합니다. 이 보관본은 서비스에서 쓰지 않습니다.</li>
            <li>학습 메모리는 저장 후 1년이 지나면 보이지 않으며, 마이페이지에서 언제든 바로 지울 수 있습니다.</li>
            <li>비회원 목표 탐색 입력값은 브라우저에서 30분 뒤 사라집니다.</li>
          </ul>
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h2 style={{ fontSize: 16 }}>5. 이용자가 할 수 있는 일</h2>
          <ul className="stack" style={{ gap: 4, paddingLeft: 18, margin: 0 }}>
            <li>저장된 학습 메모리 보기·지우기 — <Link href="/mypage" className="accent-text">마이페이지</Link></li>
            <li>알림 끄기, 알림 시간·방해금지·강도 바꾸기 — 마이페이지 → 알림 설정</li>
            <li>목표 종료, 공부 가능 시간 바꾸기 — 마이페이지 → 목표 관리</li>
            <li>회원 탈퇴 — 마이페이지 맨 아래</li>
          </ul>
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h2 style={{ fontSize: 16 }}>6. 안전하게 지키는 방법</h2>
          <p style={{ margin: 0 }}>
            모든 통신은 암호화(HTTPS)합니다. 데이터베이스는 본인 데이터만 읽을 수 있도록 행 단위 접근 제한을 걸었고,
            서버 비밀 키는 코드 저장소에 두지 않습니다. 관리자 화면에서도 이메일·닉네임·메모는 가려서 보여 줍니다.
          </p>
        </section>
      </main>
    </div>
  );
}
