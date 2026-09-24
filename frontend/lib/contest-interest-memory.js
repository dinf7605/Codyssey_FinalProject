'use client';

import { useSyncExternalStore } from 'react';

export const INTEREST_MEMORY_KEY = 'studypace.demo.contest-interests.v1';
const CHANGE_EVENT = 'studypace:contest-interests-changed';
const UNAVAILABLE = '__storage_unavailable__';

export function normalizeInterestKeywords(value) {
  if (typeof value !== 'string' || value.length > 200) {
    throw new Error('관심 키워드는 200자 이내로 입력해 주세요.');
  }
  const seen = new Set();
  return value.split(',').map((term) => term.trim()).filter((term) => {
    const key = term.toLowerCase();
    if (!term || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function getSnapshot() {
  try {
    return window.localStorage.getItem(INTEREST_MEMORY_KEY) || '';
  } catch {
    return UNAVAILABLE;
  }
}

function getServerSnapshot() {
  return null;
}

function subscribe(callback) {
  const onStorage = (event) => {
    if (event.key === INTEREST_MEMORY_KEY || event.key === null) callback();
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

function parseMemory(snapshot) {
  if (!snapshot || snapshot === UNAVAILABLE) return null;
  try {
    const data = JSON.parse(snapshot);
    if (data.version !== 1 || !Array.isArray(data.keywords) ||
        !data.keywords.every((term) => typeof term === 'string') ||
        typeof data.updatedAt !== 'string' || !Number.isFinite(Date.parse(data.updatedAt))) {
      return null;
    }
    const keywords = normalizeInterestKeywords(data.keywords.join(', '));
    return keywords.length ? { keywords, updatedAt: data.updatedAt } : null;
  } catch {
    return null;
  }
}

export function useContestInterestMemory() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const memory = parseMemory(snapshot);
  return {
    memory,
    ready: snapshot !== null,
    status: snapshot === UNAVAILABLE ? 'unavailable' : snapshot && !memory ? 'invalid' : 'ok',
  };
}

export function saveContestInterests(value) {
  const keywords = normalizeInterestKeywords(value);
  if (!keywords.length) throw new Error('저장할 관심 키워드를 먼저 입력해 주세요.');
  if (keywords.join(', ').length > 200) {
    throw new Error('쉼표와 공백을 포함해 관심 키워드를 200자 이내로 줄여 주세요.');
  }
  try {
    window.localStorage.setItem(INTEREST_MEMORY_KEY, JSON.stringify({
      version: 1,
      keywords,
      updatedAt: new Date().toISOString(),
    }));
  } catch {
    throw new Error('브라우저에 저장하지 못했습니다. 저장 공간이나 브라우저 설정을 확인해 주세요.');
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return keywords;
}

export function clearContestInterests() {
  try {
    // 다른 화면의 설정은 지우지 않고 공모전 관심 키워드만 삭제한다.
    window.localStorage.removeItem(INTEREST_MEMORY_KEY);
  } catch {
    throw new Error('저장된 키워드를 삭제하지 못했습니다. 브라우저 설정을 확인하고 다시 시도해 주세요.');
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}
