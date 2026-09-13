import { grassLevel } from '@/lib/growth';

// 공부한 날이 한 칸씩 칠해진다.
// 화면이 '풍성해지는' 감각을 만드는 핵심 장치 — 처음엔 거의 비어 있다가 기록이 쌓일수록 채워진다.
// 세로 7칸 = 월~일, 가로 한 줄 = 한 주.

const DAY_LABELS = ['월', '', '수', '', '금', '', '일'];

export default function StudyGrass({ history, weeks = 16 }) {
  const recent = history.slice(-weeks * 7);
  const firstDow = (new Date(recent[0].date).getDay() + 6) % 7;
  const cells = [...Array(firstDow).fill(null), ...recent];

  const columns = [];
  for (let i = 0; i < cells.length; i += 7) columns.push(cells.slice(i, i + 7));

  const studiedDays = recent.filter((d) => d.minutes > 0).length;

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="grass">
        <div className="grass-col" aria-hidden="true">
          {DAY_LABELS.map((label, i) => (
            <span key={i} className="micro dim" style={{ height: 11, lineHeight: '11px', width: 14 }}>
              {label}
            </span>
          ))}
        </div>

        {columns.map((col, ci) => (
          <div className="grass-col" key={ci}>
            {Array.from({ length: 7 }, (_, ri) => {
              const day = col[ri];
              if (!day) return <span key={ri} className="grass-cell" style={{ opacity: 0 }} />;
              const lv = grassLevel(day.minutes);
              return (
                <span
                  key={ri}
                  className={lv ? 'grass-cell grass-' + lv : 'grass-cell'}
                  title={day.date + ' · ' + day.minutes + '분'}
                />
              );
            })}
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="micro dim">
          최근 {weeks}주 중 {studiedDays}일 학습
        </span>
        <span className="grass-legend">
          적음
          <span className="grass-cell" />
          <span className="grass-cell grass-1" />
          <span className="grass-cell grass-2" />
          <span className="grass-cell grass-3" />
          <span className="grass-cell grass-4" />
          많음
        </span>
      </div>
    </div>
  );
}
