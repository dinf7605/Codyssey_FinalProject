'use client';

import { useEffect, useState } from 'react';
import { api, getToken } from '@/lib/api';

// FR-MY-03 알림 수신 여부 · FR-MY-05 알림 강도·방해금지 — 마이페이지
// 저장한 값은 서버 알림 워커가 알림을 보낼 때마다 읽는다 (backend/services/alarms.py).

const INTENSITY = [
  { value: 'low', label: '낮음', help: '시작 전 알림과 주간 요약만' },
  { value: 'normal', label: '보통', help: '+ 끝내지 못한 블록 알림' },
  { value: 'high', label: '높음', help: '+ 밤 9시 하루 마감 알림' },
];
const MINUTES = [5, 10, 15, 30, 60];

export default function NotificationSettings() {
  const [form, setForm] = useState(null);
  const [state, setState] = useState({ pending: false, message: '', error: '' });

  useEffect(() => {
    let alive = true;
    if (!getToken()) return undefined;
    api.settings.notifications().then(
      (data) => alive && setForm({ ...data, quiet: Boolean(data.quiet_start && data.quiet_end) }),
      () => alive && setState({ pending: false, message: '', error: '알림 설정을 불러오지 못했어요.' }),
    );
    return () => { alive = false; };
  }, []);

  if (!form) return state.error ? <p className="hint hint-error" role="alert">{state.error}</p> : null;

  function set(patch) {
    setForm((old) => ({ ...old, ...patch }));
    setState({ pending: false, message: '', error: '' });
  }

  async function save(event) {
    event.preventDefault();
    setState({ pending: true, message: '', error: '' });
    try {
      const body = {
        enabled: form.enabled,
        reminder_minutes_before: Number(form.reminder_minutes_before),
        intensity: form.intensity,
        quiet_start: form.quiet ? form.quiet_start || '22:00' : null,
        quiet_end: form.quiet ? form.quiet_end || '07:00' : null,
      };
      const saved = await api.settings.saveNotifications(body);
      setForm({ ...saved, quiet: Boolean(saved.quiet_start && saved.quiet_end) });
      setState({ pending: false, message: '알림 설정을 저장했어요.', error: '' });
    } catch (err) {
      setState({ pending: false, message: '', error: err.message || '저장하지 못했어요.' });
    }
  }

  return (
    <form className="stack" style={{ gap: 12 }} onSubmit={save} aria-label="알림 설정">
      <label style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <input type="checkbox" checked={form.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
        <span><b>학습 알림 받기</b> <span className="tiny muted">끄면 아무 알림도 보내지 않아요</span></span>
      </label>

      <fieldset disabled={!form.enabled} className="stack" style={{ gap: 12, border: 0, padding: 0, margin: 0 }}>
        <div className="field">
          <label htmlFor="noti-minutes">블록 시작 몇 분 전에 알릴까요</label>
          <select id="noti-minutes" className="input" value={form.reminder_minutes_before}
            onChange={(e) => set({ reminder_minutes_before: Number(e.target.value) })}>
            {[...new Set([...MINUTES, form.reminder_minutes_before])].sort((a, b) => a - b).map((m) => (
              <option key={m} value={m}>{m}분 전</option>
            ))}
          </select>
        </div>

        <fieldset className="stack" style={{ gap: 6, border: 0, padding: 0, margin: 0 }}>
          <legend className="tiny strong">알림 강도</legend>
          {INTENSITY.map((o) => (
            <label key={o.value} style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 14 }}>
              <input type="radio" name="intensity" value={o.value} checked={form.intensity === o.value}
                onChange={() => set({ intensity: o.value })} />
              <span><b>{o.label}</b> <span className="tiny muted">{o.help}</span></span>
            </label>
          ))}
        </fieldset>

        <div className="stack" style={{ gap: 6 }}>
          <label style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input type="checkbox" checked={form.quiet} onChange={(e) => set({ quiet: e.target.checked })} />
            <span><b>방해금지 시간</b> <span className="tiny muted">이 시간에는 알림을 보내지 않아요 (한국 시각)</span></span>
          </label>
          {form.quiet && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input type="time" className="input" aria-label="방해금지 시작" value={form.quiet_start || '22:00'}
                onChange={(e) => set({ quiet_start: e.target.value })} style={{ width: 'auto' }} />
              <span className="tiny">~</span>
              <input type="time" className="input" aria-label="방해금지 끝" value={form.quiet_end || '07:00'}
                onChange={(e) => set({ quiet_end: e.target.value })} style={{ width: 'auto' }} />
            </div>
          )}
        </div>
      </fieldset>

      {state.error && <p className="hint hint-error" role="alert">{state.error}</p>}
      {state.message && <p className="hint" role="status">{state.message}</p>}
      <button type="submit" className="btn btn-sm btn-primary" disabled={state.pending} style={{ alignSelf: 'flex-start' }}>
        {state.pending ? '저장 중…' : '알림 설정 저장'}
      </button>
    </form>
  );
}
