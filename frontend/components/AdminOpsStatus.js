'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

// 운영 상태 (평가 #3 보완, 10-07) — backend GET /admin/ops (services/ops_monitor.py)
// 준비 상태(DB 읽기 · 알림 워커 생존 신호) · 가동률(GitHub Actions uptime.yml 15분 외부 점검) · 최근 7일 서버 오류 요약.
// 대응 절차는 docs/operations.md

const READY = {
  ok: { label: '정상', cls: 'pill pill-ok' },
  degraded: { label: '일부 이상', cls: 'pill' },
  down: { label: '장애', cls: 'pill pill-late' },
};
const CHECK = { ok: '정상', stale: '멈춤 의심', unknown: '기록 없음', not_configured: '키 없음', error: '읽기 실패' };

function when(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

function percent(part) {
  return part?.uptime_percent == null ? '—' : `${part.uptime_percent}%`;
}

function Uptime({ uptime }) {
  if (uptime.status === 'unavailable') return <p className="hint" style={{ margin: 0 }}>GitHub 점검 기록을 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.</p>;
  if (uptime.status !== 'ok') return <p className="hint" style={{ margin: 0 }}>아직 외부 점검 기록이 없습니다. GitHub Actions(uptime.yml)가 15분마다 쌓습니다.</p>;
  const { day, week } = uptime;
  return (
    <div className="stack" style={{ gap: 4 }}>
      <p style={{ margin: 0 }}>
        가동률 <b className="mono">{percent(day)}</b> <span className="tiny muted">최근 24시간 · 점검 {day.checks}회 중 {day.ok}회 정상</span>
        {' · '}<b className="mono">{percent(week)}</b> <span className="tiny muted">7일 · {week.checks}회 중 {week.ok}회</span>
      </p>
      {week.incidents.length > 0 ? (
        <ul className="tiny" style={{ margin: 0, paddingLeft: 18 }}>
          {week.incidents.slice(-3).reverse().map((i) => (
            <li key={i.start}>
              <a href={i.url} target="_blank" rel="noreferrer">{when(i.start)}</a>
              {i.end ? ` 부터 약 ${i.minutes}분 장애` : ' 부터 장애 — 아직 복구되지 않음'} (실패한 점검 {i.failed_checks}회)
            </li>
          ))}
        </ul>
      ) : <p className="tiny muted" style={{ margin: 0 }}>최근 7일 장애 없음</p>}
      <a className="tiny" href={uptime.workflow_url} target="_blank" rel="noreferrer">점검 기록 전체 보기 (GitHub Actions)</a>
    </div>
  );
}

function Errors({ errors }) {
  if (errors.status === 'unavailable') return <p className="hint" style={{ margin: 0 }}>서버 오류 기록을 불러오지 못했습니다. (migration 020 적용 여부 확인)</p>;
  if (errors.status === 'empty') return <p className="hint" style={{ margin: 0 }}>최근 {errors.days}일 서버 오류(5xx · 처리되지 않은 예외 · 워커 작업 실패)가 없습니다.</p>;
  const peak = Math.max(1, ...errors.by_day.map((d) => d.count));
  return (
    <div className="stack" style={{ gap: 8 }}>
      <p style={{ margin: 0 }}>
        최근 {errors.days}일 서버 오류 <b className="mono">{errors.total}건</b>
        <span className="tiny muted">
          {' '}{Object.entries(errors.by_source).map(([k, n]) => `${k === 'api' ? 'API' : '알림 워커'} ${n}건`).join(' · ')}
          {errors.by_type.length > 0 && ` · 많은 유형: ${errors.by_type.slice(0, 3).map((t) => `${t.name} ${t.count}`).join(', ')}`}
        </span>
      </p>
      <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 40 }} aria-label="날짜별 오류 건수">
        {errors.by_day.map((d) => (
          <div key={d.day} title={`${d.day} ${d.count}건`} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <div className="bar-fill" style={{ width: '100%', height: `${Math.max(2, (d.count / peak) * 28)}px`, borderRadius: 2 }} />
            <span className="tiny muted" style={{ fontSize: 10 }}>{d.day.slice(5)}</span>
          </div>
        ))}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="db-table">
          <thead><tr><th>시각</th><th>경로</th><th>상태</th><th>유형</th><th>요청 번호</th></tr></thead>
          <tbody>
            {errors.recent.slice(0, 5).map((r) => (
              <tr key={`${r.occurred_at}-${r.request_id || r.route}`}>
                <td>{when(r.occurred_at)}</td>
                <td className="mono">{`${r.method || ''} ${r.route}`.trim()}</td>
                <td>{r.status_code || '—'}</td>
                <td>{r.error_type}</td>
                <td className="mono">{r.request_id || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AdminOpsStatus() {
  const [result, setResult] = useState(null);

  useEffect(() => {
    let alive = true;
    api.admin.ops().then(
      (data) => alive && setResult({ data }),
      (err) => alive && setResult({ error: err.status === 403 ? '관리자 권한이 필요합니다.' : '운영 상태를 불러오지 못했습니다.' }),
    );
    return () => { alive = false; };
  }, []);

  if (!result) return <p role="status" className="hint">운영 상태를 확인하고 있습니다.</p>;
  if (result.error) return <p role="alert" className="hint hint-error">{result.error}</p>;
  const { ready, uptime, errors } = result.data;
  const view = READY[ready.status] || READY.ok;
  const worker = ready.worker || {};

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }} role={ready.status === 'ok' ? undefined : 'alert'}>
        <span className={view.cls}>{view.label}</span>
        <span className="tiny muted">
          DB {CHECK[ready.checks.db] || ready.checks.db} · 알림 워커 {CHECK[ready.checks.worker] || ready.checks.worker}
          {worker.last_beat_minutes != null && ` (${worker.last_beat_minutes}분 전 신호)`}
          {' · '}버전 <span className="mono">{ready.version}</span> · 서버 시작 {when(ready.started_at)}
        </span>
      </div>
      <Uptime uptime={uptime} />
      <Errors errors={errors} />
    </div>
  );
}
