import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';

// TypeScript를 안 쓰는 대신 ESLint가 안전망 역할을 한다 (docs/학습로드맵.md 1-②)
// Next.js 16부터 `next lint` 명령이 없어져 flat config를 직접 불러온다.
const config = [
  ...nextCoreWebVitals,
  { ignores: ['.next/**', 'node_modules/**'] },
];

export default config;
