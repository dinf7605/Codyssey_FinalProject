// 공모전 화면 공통 도우미 (FR-CONT-03 검색 · FR-CONT-10 준비 기간)
//
// 공고는 위비티에서 모은 사실 정보(제목·주최·분야·접수기간·응모대상·링크)다. 마감일이 비어 있는 옛 링크 전용 행만 예외.
// 본문은 저장하지 않으므로 자세한 내용은 항상 원문 링크로 보낸다.

import { api } from './api';
import { ddayOf, kstToday } from './planView';

export const SOURCE_LABEL = { wevity: '위비티' };

/** 마감까지 남은 날 (한국 날짜 기준, 오늘 마감이면 0) */
export const daysLeft = (deadline) => deadline ? ddayOf(deadline, kstToday()) : null;

/** http(s) 링크만 연다 — 수집한 값이라 한 번 걸러서 쓴다 */
export function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

/** 키워드 여러 개로 찾는다 — 키워드마다 검색해서 합치고, 많이 맞은 공고부터 · 같으면 마감 임박순 */
export async function searchByKeywords(keywords, options = {}) {
  if (!keywords.length) {
    const res = await api.contests.search({ limit: 20 }, options);
    return { items: res.items.map((c) => ({ ...c, matched: [] })), total: res.total };
  }
  const res = await api.contests.recommend(keywords.slice(0, 10).join(', '));
  const items = res.items.map((item) => ({
    ...item.contest, matched: item.matching_tags, reason: item.reason,
    aiGenerated: res.method === 'title_claude',
  }));
  return { items, total: items.length };
}
