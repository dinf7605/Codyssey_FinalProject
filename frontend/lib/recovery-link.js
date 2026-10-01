// Supabase implicit recovery 링크만 받는다. 토큰의 진위는 서버가 검증한다.
export function parseRecoveryLink(hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  if (params.has('error') || params.has('error_code')) return null;
  const accessToken = params.get('access_token');
  const refreshToken = params.get('refresh_token');
  return params.get('type') === 'recovery' && accessToken && refreshToken
    ? { accessToken, refreshToken } : null;
}
