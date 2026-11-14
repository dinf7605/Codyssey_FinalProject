// 로그인·가입 뒤 돌아갈 곳(?next=) — 우리 사이트 안의 경로만 받는다.
// '//evil.com' 같은 주소로 내보내는 데 쓰이지 않게, 브라우저가 주소를 읽는 방식 그대로 풀어 보고 판단한다.

const BASE = 'http://studypace.invalid'; // 경로를 풀어 볼 때만 쓰는 가짜 출처 (실제로 요청하지 않는다)

function hasControlChar(text) {
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code < 0x20 || code === 0x7f) return true;
  }
  return false;
}

// 받을 수 있으면 정리된 경로('/study?tab=1')를, 아니면 null 을 돌려준다
export function safeNext(value) {
  if (typeof value !== 'string' || !value.startsWith('/')) return null;
  // 탭·개행 같은 제어 문자는 브라우저가 지워 버려 '/<탭>/evil.com' 이 '//evil.com' 이 된다
  if (hasControlChar(value)) return null;
  try {
    const url = new URL(value, BASE);
    // '//evil.com' · '/\evil.com' 은 여기서 다른 출처로 풀린다
    if (url.origin !== BASE) return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}
