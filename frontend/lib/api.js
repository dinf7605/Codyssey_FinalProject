// FastAPI 백엔드 호출 래퍼.
// 화면 코드가 fetch를 직접 쓰지 않게 해서, 주소가 바뀌어도 이 파일만 고치면 된다.
//
// 로컬:  NEXT_PUBLIC_API_BASE=http://localhost:8000
// 배포:  Railway 주소 (Vercel 환경변수에 등록 — docs/학습로드맵.md 6-②)

const BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });

  if (!res.ok) {
    // 에러를 그냥 삼키지 않는다. 화면에서 사용자에게 무엇이 잘못됐는지 보여줘야 한다.
    let detail = `요청이 실패했습니다 (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* 응답이 JSON이 아니면 기본 문구를 쓴다 */
    }
    throw new Error(detail);
  }

  return res.status === 204 ? null : res.json();
}

export const api = {
  health: () => request('/health'),

  contests: {
    demoList: (keywords = '', options = {}) =>
      request('/demo/contests?' + new URLSearchParams({ keywords }), options),
  },

  // 아래는 백엔드 라우터가 채워지는 대로 연결한다.
  // 지금은 화면이 목업 데이터로 동작하므로 호출하지 않는다.
  auth: {
    ping: () => request('/auth/ping'),
  },
  batch: {
    ping: () => request('/batch/ping'),
  },
};

export default api;
