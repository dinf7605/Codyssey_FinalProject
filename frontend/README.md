# StudyPace 프론트엔드

Next.js 16 (App Router) + React 19 + **JavaScript**
모바일이 주력이므로 모바일 화면을 기준으로 만들고 데스크톱에서 넓히는 방식이다.

## 실행

```bash
cd frontend
npm install
npm run dev     # http://localhost:3000
```

| 명령 | 설명 |
|---|---|
| `npm run dev` | 개발 서버 |
| `npm run build` | 배포용 빌드 |
| `npm run lint` | ESLint 검사 — TypeScript를 안 쓰는 대신 이게 안전망이다 |

> `next lint` 명령은 Next.js 16에서 제거됐다. `npm run lint`가 `eslint .`를 직접 부른다.

### 환경변수

`frontend/.env.local` 을 만들고 백엔드 주소를 넣는다. (`.env.local`은 커밋되지 않는다)

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

배포할 때는 **Vercel 대시보드에도 같은 값을 등록**해야 한다.
빠뜨리면 "로컬에선 되는데 배포하면 안 되는" 상황이 된다 (`docs/학습로드맵.md` 6-②).

## 폴더 구조

```
frontend/
├── app/
│   ├── layout.js              루트 레이아웃 · 뷰포트 · 적응형 테마 적용
│   ├── globals.css            디자인 토큰 + 전체 스타일
│   ├── page.js                랜딩 (비회원 첫 화면)
│   ├── login/ · signup/       인증
│   ├── onboarding/            목표 탐색 3단계 (파이프라인 0)
│   └── (app)/                 로그인 후 화면 — 상단바 + 하단 탭 공통 적용
│       ├── dashboard/         오늘의 학습 · 진도 신호등
│       ├── schedule/          주간 일정 · 야간 재조정 내역
│       ├── study/             학습 타이머
│       ├── contests/          공모전 검색 · 상세(준비 기간 계산)
│       ├── mypage/            메모리 · 설정
│       └── admin/             AI 호출 모니터링
├── components/                화면에서 공통으로 쓰는 조각
├── lib/
│   ├── api.js                 FastAPI 호출 래퍼
│   ├── mock.js                임시 데이터 — 백엔드 연결되면 삭제
│   └── ui.js                  적응형 밀도 · 진도 상태 · D-day 계산
└── eslint.config.mjs
```

`(app)` 처럼 괄호가 붙은 폴더는 **URL에 나타나지 않는다.** 레이아웃만 공유하기 위한 묶음이다.
`app/(app)/dashboard/page.js` → `/dashboard`

## 화면 ↔ 기능 ID

| 경로 | 화면 | 기능 |
|---|---|---|
| `/` | 랜딩 | 비회원 진입 · 받게 될 일정 미리보기 |
| `/onboarding` | 목표 탐색 | `FR-GOAL-01` `FR-GOAL-02` `FR-GOAL-05` `FR-GOAL-11` |
| `/login` `/signup` | 인증 | `FR-AUTH-01~03` `FR-JOIN-01~03` |
| `/dashboard` | 대시보드 | `FR-MAIN-03~05` `FR-PACE-04` |
| `/schedule` | 일정 | `FR-PLAN-04` `FR-PLAN-05` `FR-PLAN-07` `FR-PACE-01` |
| `/study` | 학습 실행 | `FR-STUDY-01` `FR-STUDY-02` `FR-STUDY-05` |
| `/contests` | 공모전 목록 | `FR-CONT-03` `FR-CONT-04` `FR-CONT-05` |
| `/contests/[id]` | 공모전 상세 | `FR-CONT-10` `FR-CONT-11` |
| `/mypage` | 마이페이지 | `FR-MEM-01` `FR-MEM-02` `FR-MY-01~05` |
| `/admin` | 관리자 | `FR-ADMIN-01` `FR-ADMIN-02` |

## 모바일 대응

| 항목 | 처리 |
|---|---|
| 기본 내비게이션 | 하단 탭 4개. 데스크톱(900px~)에서는 상단 가로 탭으로 바뀐다 |
| 노치 · 홈바 | `viewportFit: cover` + CSS `env(safe-area-inset-*)` |
| 터치 타깃 | 버튼 최소 높이 48px |
| 입력 확대 방지 | `.input` 글자 크기 16px — iOS는 16px 미만이면 포커스 시 화면을 확대한다 |
| 확대 허용 | `maximumScale: 5` — 확대를 막지 않는다 (접근성) |
| 가로 스크롤 | `body { overflow-x: hidden }` + 칩 줄은 `.scroller`로 개별 스크롤 |

## 디자인 토큰

색·간격·글꼴은 전부 `globals.css` 상단의 CSS 변수로 관리한다.
**개별 컴포넌트에 색을 직접 쓰지 않는다** — 다크 모드가 깨진다.

```css
color: var(--ink-2);        /* 좋음 */
color: #4E5866;             /* 나쁨 — 다크 모드에서 안 보인다 */
```

### 적응형 UI (`FR-UI-01` · `FR-UI-02`)

`<html>`의 `data-level`(1~5)과 `data-density`가 강조색과 여백 배율을 바꾼다.
레벨이 올라가도 **명도 대비는 유지**한다 (`NFR-A11Y-01`).

## 지켜야 할 것

1. **AI가 만든 내용에는 `AiBadge`와 `AiNotice`를 반드시 붙인다** (`NFR-ETHIC-01`)
   숨김·접기 기능을 넣지 않는다.
2. **상태를 색으로만 구분하지 않는다** (`NFR-A11Y-01`)
   진도 신호등도 색 + 문구를 함께 쓴다.
3. **빈 상태를 비워두지 않는다** — `EmptyState`로 다음 행동을 제시한다.
4. **에러를 삼키지 않는다** — `lib/api.js`가 실패 사유를 던지면 화면에서 보여준다.

## 지금 상태

- 화면과 흐름은 전부 만들어져 있고 **데이터는 `lib/mock.js`의 예시값**이다.
- 백엔드가 붙는 순서대로 `lib/api.js` 호출로 바꾸면 된다.
- 로그인·가입 폼은 화면만 있고 제출 동작은 아직 연결되지 않았다.
