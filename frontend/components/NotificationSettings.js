'use client';

import { useEffect, useState } from 'react';
import { api, getToken } from '@/lib/api';
import { browserAlertState, requestBrowserAlerts } from '@/lib/browserAlerts';

// FR-MY-03 알림 3종(재조정 결과 · 마감 임박 · 학습 독촉) · FR-MY-05 알림 강도·방해금지·전체 끄기 — 마이페이지
// 저장한 값은 서버 알림 워커가 알림을 보낼 때마다 읽는다 (backend/services/alarms.py).
// 선택 항목 3종은 저장한 적이 없으면 가입 때 '학습 알림 수신(선택)' 동의를 따른다.

const INTENSITY = [
  { value: 'low', label: '약', help: '블록 시작 알림만' },
  // 재조정 결과·학습 독촉은 강도로 '받을 수 있게' 될 뿐, 아래 선택 알림에서 켜야 온다 —
  // 예전 문구는 기본으로 오는 것처럼 읽혀 체크가 꺼져 있는 게 어긋나 보였다 (10-02 test05)
  { value: 'normal', label: '보통', help: '+ 주간 요약 (기본) · 아래에서 켜면 재조정 결과' },
  { value: 'high', label: '강', help: '+ 아래에서 켜면 학습 독촉 (끝내지 못한 블록 · 밤 9시 하루 마감)' },
];
const MINUTES = [5, 10, 15, 30, 60];

function Toggle({ checked, onChange, title, help, disabled = false }) {
  return (
    <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', opacity: disabled ? 0.6 : 1 }}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} style={{ marginTop: 3 }} />
      <span><b>{title}</b> <span className="tiny muted">{help}</span></span>
    </label>
  );
}

export default function NotificationSettings() {
  const [form, setForm] = useState(null);
  const [state, setState] = useState({ pending: false, message: '', error: '' });
  const [browser, setBrowser] = useState(() => browserAlertState());

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

  async function allowBrowser() {
    setBrowser(await requestBrowserAlerts());
  }

  async function save(event) {
    event.preventDefault();
    setState({ pending: true, message: '', error: '' });
    try {
      const body = {
        enabled: form.enabled,
        reminder_minutes_before: Number(form.reminder_minutes_before),
        intensity: form.intensity,
        quiet_start: form.quiet ? form.quiet_start || '23:00' : null,
        quiet_end: form.quiet ? form.quiet_end || '07:00' : null,
        notify_replan: form.notify_replan,
        notify_deadline: form.notify_deadline,
        notify_nudge: form.notify_nudge,
      };
      const saved = await api.settings.saveNotifications(body);
      setForm({ ...saved, quiet: Boolean(saved.quiet_start && saved.quiet_end) });
      setState({ pending: false, message: '알림 설정을 저장했어요. 다음 알림부터 바로 적용돼요.', error: '' });
    } catch (err) {
      setState({ pending: false, message: '', error: err.message || '저장하지 못했어요.' });
    }
  }

  return (
    <form className="stack" style={{ gap: 12 }} onSubmit={save} aria-label="알림 설정">
      <Toggle checked={form.enabled} onChange={(v) => set({ enabled: v })}
        title="학습 알림 받기" help="끄면 학습 알림을 보내지 않아요 (아래 공모전 마감 알림은 따로 정해요)" />

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

        <fieldset className="stack" style={{ gap: 6, border: 0, padding: 0, margin: 0 }}>
          <legend className="tiny strong">일정 변경 · 독촉 알림</legend>
          <Toggle checked={form.notify_replan} onChange={(v) => set({ notify_replan: v })}
            title="재조정 결과" help="밤사이 블록을 옮기면 아침에 알려요" disabled={form.intensity === 'low'} />
          <Toggle checked={form.notify_nudge} onChange={(v) => set({ notify_nudge: v })}
            title="학습 독촉" help={form.intensity === 'high' ? '하루 최대 3번, 2번 연달아 안 보면 그날은 멈춰요' : "강도 '강'에서 보내요"}
            disabled={form.intensity !== 'high'} />
        </fieldset>

        <div className="stack" style={{ gap: 6 }}>
          <Toggle checked={form.quiet} onChange={(v) => set({ quiet: v })}
            title="방해금지 시간" help="이 시간에는 보내지 않고, 끝난 뒤 첫 알림에 합쳐 알려요 (한국 시각)" />
          {form.quiet && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input type="time" className="input" aria-label="방해금지 시작" value={form.quiet_start || '23:00'}
                onChange={(e) => set({ quiet_start: e.target.value })} style={{ width: 'auto' }} />
              <span className="tiny">~</span>
              <input type="time" className="input" aria-label="방해금지 끝" value={form.quiet_end || '07:00'}
                onChange={(e) => set({ quiet_end: e.target.value })} style={{ width: 'auto' }} />
            </div>
          )}
        </div>
      </fieldset>

      <Toggle checked={form.notify_deadline} onChange={(v) => set({ notify_deadline: v })}
        title="관심 공모전 마감 임박" help="관심 등록한 공모전 마감 24시간 전에 알려요. 학습 알림을 꺼도 따로 받을 수 있어요" />

      <p className="tiny muted" style={{ margin: 0 }}>
        알림은 이 사이트 안(머리글의 알림)에 쌓여요.{' '}
        {browser === 'granted' && '이 브라우저에서 사이트를 열어 두면 브라우저 알림으로도 띄워요.'}
        {browser === 'denied' && '브라우저 알림은 꺼져 있어요. 브라우저 설정에서 다시 허용할 수 있어요.'}
        {browser === 'unsupported' && '이 브라우저는 브라우저 알림을 지원하지 않아요.'}
      </p>
      {browser === 'default' && (
        <button type="button" className="btn btn-sm" onClick={allowBrowser} style={{ alignSelf: 'flex-start' }}>
          브라우저 알림도 받기
        </button>
      )}

      {state.error && <p className="hint hint-error" role="alert">{state.error}</p>}
      {state.message && <p className="hint" role="status">{state.message}</p>}
      <button type="submit" className="btn btn-sm btn-primary" disabled={state.pending} style={{ alignSelf: 'flex-start' }}>
        {state.pending ? '저장 중…' : '알림 설정 저장'}
      </button>
    </form>
  );
}
