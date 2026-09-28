'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

const TOKEN_LABELS = {
  input_tokens: '입력 토큰',
  output_tokens: '출력 토큰',
  cache_creation_input_tokens: '캐시 생성 입력 토큰',
  cache_read_input_tokens: '캐시 읽기 입력 토큰',
};
const STATUS_MESSAGES = {
  disabled: '새 AI 요청 기록 저장이 꺼져 있습니다. 저장 활성화 후 통계를 조회할 수 있습니다.',
  empty: '선택한 날짜에 저장된 AI 요청 기록이 없습니다. 실패율은 계산하지 않습니다.',
  unavailable: 'AI 요청 통계를 집계하지 못했습니다. DB 연동 및 테이블 적용 상태를 확인해 주세요.',
  limit_exceeded: '조회 범위를 초과해 집계하지 못했습니다. 하루 20,000건 또는 조회 횟수 제한이 적용됩니다.',
};

export default function AdminRequestMetrics({ day, revision }) {
  const [result, setResult] = useState(null);
  const key = `${day}:${revision}`;
  useEffect(() => {
    let active = true;
    api.admin.requestMetrics({ day }).then(
      (data) => { if (active) setResult({ key, data }); },
      (error) => {
        if (active) setResult({ key, error: error.status === 401
          ? '로그인이 필요하거나 로그인 시간이 만료되었습니다.'
          : error.status === 403 ? '관리자 권한이 필요합니다.'
            : 'AI 요청 통계를 불러오지 못했습니다. 새로고침해 주세요.' });
      },
    );
    return () => { active = false; };
  }, [day, revision, key]);

  if (result?.key !== key) return <p role="status">AI 요청 통계를 확인하고 있습니다.</p>;
  if (result.error) return <p role="alert">{result.error}</p>;
  const data = result.data;
  if (data.status !== 'ok') {
    return <p role="status">{STATUS_MESSAGES[data.status] || STATUS_MESSAGES.unavailable}</p>;
  }
  const summary = data.summary;
  return (
    <>
      <p className="hint">{data.day} · 학습 분해에 저장된 요청 기준입니다. 재시도도 각각 1회로 집계합니다.</p>
      <dl style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div><dt>AI 요청 수</dt><dd>{summary.request_count.toLocaleString('ko-KR')}회</dd></div>
        <div><dt>응답 수신 성공</dt><dd>{summary.succeeded_count.toLocaleString('ko-KR')}회</dd></div>
        <div><dt>AI 요청 실패</dt><dd>{summary.failed_count.toLocaleString('ko-KR')}회</dd></div>
        <div><dt>AI 요청 실패율</dt><dd>{summary.failure_rate_percent == null ? '집계 불가' : `${summary.failure_rate_percent}%`}</dd></div>
      </dl>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', textAlign: 'left' }}>
          <caption>응답에서 확인된 토큰 사용량</caption>
          <thead><tr><th scope="col">항목</th><th scope="col">기록된 합계</th><th scope="col">값이 기록된 요청</th></tr></thead>
          <tbody>{Object.entries(TOKEN_LABELS).map(([field, label]) => {
            const item = summary.tokens[field];
            return <tr key={field}>
              <th scope="row">{label}</th>
              <td>{item.total == null ? '미기록' : `${item.total.toLocaleString('ko-KR')} 토큰`}</td>
              <td>{item.record_count.toLocaleString('ko-KR')} / {summary.request_count.toLocaleString('ko-KR')}회</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <p className="hint">요청 성공은 응답 수신 기준이며, 학습 계획 생성 성공과 다릅니다.
        토큰 값이 누락된 요청은 합계에서 제외됩니다. 저장 누락이 있을 수 있어 전체 사용량이나 청구 비용을 나타내지 않습니다.</p>
    </>
  );
}
