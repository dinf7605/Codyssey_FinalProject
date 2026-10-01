'use client';

import { useSyncExternalStore } from 'react';
import { getToken, TOKEN_KEY } from './api';

function subscribe(callback) {
  const onStorage = (event) => {
    if (event.key === TOKEN_KEY || event.key === null) callback();
  };
  window.addEventListener('storage', onStorage);
  return () => window.removeEventListener('storage', onStorage);
}

export function useAuthToken() {
  return useSyncExternalStore(subscribe, getToken, () => null);
}
