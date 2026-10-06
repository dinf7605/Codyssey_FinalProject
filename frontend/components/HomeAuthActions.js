'use client';

import Link from 'next/link';
import { useAuthToken } from '@/lib/auth-token';

// 첫 화면 헤더 — 로그인했으면 '로그인 / 회원가입' 대신 내 학습으로 가는 버튼 (10-06)
export default function HomeAuthActions() {
  const token = useAuthToken();
  if (token) {
    return (
      <>
        <Link href="/mypage" className="btn btn-quiet btn-sm">마이페이지</Link>
        <Link href="/dashboard" className="btn btn-sm">내 학습 보기</Link>
      </>
    );
  }
  return (
    <>
      <Link href="/login" className="btn btn-quiet btn-sm">로그인</Link>
      <Link href="/signup" className="btn btn-sm">회원가입</Link>
    </>
  );
}
