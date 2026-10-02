'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, clearAuthTokens, getToken } from '@/lib/api';
import { clearContestPlanning } from '@/lib/contest-planning';
import { clearExploration } from '@/lib/goalSession';
import { clearDraft } from '@/lib/planDraft';

// 로그아웃·탈퇴 때 이 계정이 고른 목표·만들던 계획·레벨 표시까지 지운다.
// 남겨 두면 공용 PC 에서 다음 비회원에게 앞사람의 목표(시험일·가용시간)가 그대로 보였다 (10-01 실사용).
// 학습 타이머 기록은 계정별(owner)로 남아 그 사람이 다시 로그인하면 보내므로 지우지 않는다.
export function signOut() {
  clearAuthTokens();
  clearExploration();
  clearDraft();
  clearContestPlanning();
  try { window.localStorage.removeItem('sp_level'); } catch { /* 저장소가 차단된 브라우저 */ }
}

export default function AccountSettings() {
  const router = useRouter();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    api.settings.profile().then(setProfile).catch((err) => {
      // 프로필 행이 없는 계정(가입 중 프로필 저장이 실패했거나 관리자가 만든 계정)도 쓸 수는 있다 — 오류로 보이지 않는다
      if (err.status === 404) setProfile({ nickname: null, email: null });
      else setError('프로필을 불러오지 못했습니다.');
    });
  }, []);

  function logout() {
    signOut();
    router.push('/login');
  }

  async function withdraw() {
    if (pending) return;
    if (!window.confirm('탈퇴하면 서비스 이용이 종료되고 일정·학습기록·알림이 삭제됩니다. 이메일·닉네임·약관 동의 정보는 별도로 1년간 보관한 뒤 삭제됩니다. 탈퇴하시겠습니까?')) return;
    setPending(true);
    setError('');
    try {
      await api.settings.withdraw();
      signOut();
      window.alert('탈퇴가 완료되었습니다. 이메일·닉네임·약관 동의 정보는 별도로 1년간 보관한 뒤 삭제됩니다.');
      router.replace('/');
    } catch {
      setError('탈퇴 처리를 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="sec">
      <div className="rows">
        {profile && <div className="row"><div className="row-main"><b>내 계정</b><span>{[profile.nickname || '닉네임 미등록', profile.email].filter(Boolean).join(' · ')}</span></div></div>}
        {/* 로그인한 채로 비밀번호를 바꿀 길이 없었다 — 재설정 메일 화면으로 보낸다 (10-02 test05) */}
        <div className="row">
          <div className="row-main"><b>비밀번호 바꾸기</b><span>가입한 이메일로 새 비밀번호를 정하는 링크를 보내 드려요</span></div>
          <Link className="btn btn-sm" style={{ flexShrink: 0 }} href="/forgot-password">바꾸기</Link>
        </div>
        <div className="row">
          <div className="row-main"><b>로그아웃</b><span>이 브라우저의 로그인 정보를 지웁니다</span></div>
          <button type="button" className="btn btn-sm" onClick={logout} disabled={pending}>로그아웃</button>
        </div>
        <div className="row">
          <div className="row-main"><b className="muted">회원 탈퇴</b><span>프로필은 별도로 1년 보관 후 삭제하며, 일정·학습기록·알림은 탈퇴 시 삭제합니다</span></div>
          <button type="button" className="btn btn-sm" onClick={withdraw} disabled={pending}>
            {pending ? '처리 중...' : '회원 탈퇴'}
          </button>
        </div>
      </div>
      {error && <p role="alert" className="hint">{error}</p>}
    </section>
  );
}
