// 가입과 재설정에서 동일한 규칙을 사용한다. 비밀번호는 trim하지 않는다.
export function passwordChecks(value) {
  return [
    { label: '8~64자', met: [...value].length >= 8 && [...value].length <= 64 },
    { label: '영문 포함', met: /[A-Za-z]/.test(value) },
    { label: '숫자 포함', met: /[0-9]/.test(value) },
    { label: '특수문자 포함', met: /[^A-Za-z0-9]/.test(value) },
  ];
}
export function passwordValid(value) {
  return passwordChecks(value).every((rule) => rule.met);
}
export function authErrorMessage(error, action) {
  if (!error.status) return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.';
  if (error.status === 429) return '요청이 너무 많습니다. 잠시 기다린 뒤 다시 시도해 주세요.';
  if (action === 'signup' && error.status === 409) return '이미 가입된 이메일입니다. 로그인하거나 비밀번호를 재설정해 주세요.';
  if (error.status === 422) {
    const fields = (error.validationErrors || []).flatMap((item) => item.loc || []);
    if (fields.includes('password') || fields.includes('new_password')) return '비밀번호는 8~64자로 영문·숫자·특수문자를 포함해야 합니다.';
    if (fields.includes('email')) return '이메일 주소 형식을 확인해 주세요.';
    if (fields.includes('nickname')) return '닉네임은 2~10자로 입력해 주세요.';
    return '입력한 정보를 확인해 주세요.';
  }
  // 서버가 사용자에게 보여주도록 정리한 400 응답만 표시한다.
  if (error.status === 400) return error.message;
  return action === 'signup'
    ? '가입 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.'
    : '비밀번호 재설정을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.';
}
