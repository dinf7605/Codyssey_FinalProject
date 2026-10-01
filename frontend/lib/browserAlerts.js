// FR-ALARM-01 브라우저 알림 — 사이트를 열어 둔 브라우저에 새 학습 알림을 띄운다.
// 푸시 서버 없이 브라우저 기본 Notification 만 쓴다. 사이트가 닫혀 있으면 앱 안 알림(/notifications)에만 쌓인다.
//
//  - 권한은 사용자가 버튼을 눌렀을 때 한 번만 묻는다. 거부하면 다시 묻지 않는다 (브라우저 설정에서만 되돌릴 수 있다)
//  - 같은 알림을 두 번 띄우지 않게 마지막으로 띄운 알림 id 를 이 브라우저에 둔다
//  - 누르면 블록 알림은 그 블록 타이머로, 나머지는 알림 화면으로 간다

const ASKED_KEY = 'sp_browser_alert_asked';
const LAST_KEY = 'sp_browser_alert_last_id';

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function browserAlertState() {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported';
  return window.Notification.permission; // 'default' · 'granted' · 'denied'
}

export function alreadyAsked() {
  return storage()?.getItem(ASKED_KEY) === '1';
}

export async function requestBrowserAlerts() {
  if (browserAlertState() !== 'default') return browserAlertState();
  try { storage()?.setItem(ASKED_KEY, '1'); } catch { /* 저장 못 해도 묻기는 한다 */ }
  try {
    return await window.Notification.requestPermission();
  } catch {
    return browserAlertState();
  }
}

// 처음 불렀을 때는 지금까지 쌓인 알림을 띄우지 않고 기준만 잡는다 — 접속할 때마다 옛 알림이 쏟아지지 않게.
export function showNewAlerts(rows) {
  const box = storage();
  if (!box || !rows?.length) return;
  const newest = Math.max(...rows.map((r) => Number(r.id) || 0));
  const last = Number(box.getItem(LAST_KEY) || 0);
  try { box.setItem(LAST_KEY, String(Math.max(newest, last))); } catch { /* 다음에 다시 센다 */ }
  if (!last || browserAlertState() !== 'granted') return;
  rows
    .filter((r) => Number(r.id) > last && !r.is_read && r.type !== 'rest_today')
    .slice(0, 3)
    .forEach((r) => {
      const alert = new window.Notification('StudyPace', { body: r.message, tag: `sp-${r.id}` });
      alert.onclick = () => {
        window.focus();
        window.location.href = r.block_id ? `/study?block=${encodeURIComponent(r.block_id)}` : '/notifications';
        alert.close();
      };
    });
}
