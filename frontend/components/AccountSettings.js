'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, clearAuthTokens, getToken } from '@/lib/api';

export default function AccountSettings() {
  const router = useRouter();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    api.settings.profile().then(setProfile).catch(() => setError('프로필을 불러오지 못했습니다.'));
  }, []);

  function logout() {
    clearAuthTokens();
    router.push('/login');
  }

  async function withdraw() {
    if (!window.confirm('계정과 학습 데이터를 삭제합니다. 탈퇴하시겠습니까?')) return;
    setPending(true);
    setError('');
    try {
      await api.settings.withdraw();
      clearAuthTokens();
      router.push('/');
    } catch {
      setError('탈퇴 처리를 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="sec">
      <div className="rows">
        {profile && <div className="row"><div className="row-main"><b>내 계정</b><span>{profile.nickname} · {profile.email}</span></div></div>}
        <div className="row">
          <div className="row-main"><b>로그아웃</b><span>이 브라우저의 로그인 정보를 지웁니다</span></div>
          <button type="button" className="btn btn-sm" onClick={logout}>로그아웃</button>
        </div>
        <div className="row">
          <div className="row-main"><b className="muted">회원 탈퇴</b><span>계정과 연결된 일정·학습기록·알림을 삭제합니다</span></div>
          <button type="button" className="btn btn-sm" onClick={withdraw} disabled={pending}>
            {pending ? '처리 중...' : '회원 탈퇴'}
          </button>
        </div>
      </div>
      {error && <p role="alert" className="hint">{error}</p>}
    </section>
  );
}
