'use client';

import { passwordChecks, passwordValid } from '@/lib/password-feedback';

export default function PasswordFields({
  idPrefix, password, confirmation, onPasswordChange, onConfirmationChange,
  disabled = false, label = '비밀번호',
}) {
  const mismatch = confirmation.length > 0 && password !== confirmation;
  const color = (met) => met ? '#15803d' : '#dc2626';
  return (
    <>
      <div className="field">
        <label htmlFor={`${idPrefix}-password`}>{label}</label>
        <input id={`${idPrefix}-password`} name="password" type="password" className="input"
          autoComplete="new-password" required minLength={8} maxLength={64}
          value={password} onChange={(event) => onPasswordChange(event.target.value)} disabled={disabled}
          aria-describedby={`${idPrefix}-rules`} aria-invalid={password.length > 0 && !passwordValid(password)} />
        <ul id={`${idPrefix}-rules`} className="hint" aria-live="polite" aria-atomic="true"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', listStyle: 'none', padding: 0, margin: '6px 0 0' }}>
          {passwordChecks(password).map(({ label: rule, met }) => (
            <li key={rule} style={{ color: color(met) }}>{met ? '✓ 충족' : '✗ 필요'} · {rule}</li>
          ))}
        </ul>
      </div>
      <div className="field">
        <label htmlFor={`${idPrefix}-confirmation`}>{label} 확인</label>
        <input id={`${idPrefix}-confirmation`} name="passwordConfirm" type="password" className="input"
          autoComplete="new-password" required maxLength={64} value={confirmation}
          onChange={(event) => onConfirmationChange(event.target.value)} disabled={disabled}
          aria-describedby={`${idPrefix}-match`} aria-invalid={mismatch} />
        <p id={`${idPrefix}-match`} className="hint" aria-live="polite"
          style={{ color: confirmation ? color(!mismatch) : undefined, marginTop: 6 }}>
          {confirmation ? (mismatch ? '비밀번호가 일치하지 않습니다.' : '✓ 비밀번호가 일치합니다.') : '같은 비밀번호를 한 번 더 입력해 주세요.'}
        </p>
      </div>
    </>
  );
}
