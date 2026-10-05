'use client';

import { useEffect, useId, useRef, useState } from 'react';
import styles from './SignupConsentFields.module.css';

// Review content against actual service operations before public release.
// This is collection/use consent and feature guidance, not a complete privacy policy.
//
// FR-JOIN-03 — ai 항목 문구를 바꾸면 backend/routers/auth.py 의 AI_NOTICE_VERSION 도 올린다.
// 버전이 다르면 다음 로그인 때 components/ReconsentGate.js 가 다시 동의를 받는다.
export const CONTENT = {
  privacy: {
    title: '개인정보 수집·이용 동의',
    label: '필수',
    summary: '수집하는 정보, 이용 목적과 보관 기간을 확인해 주세요.',
    introduction: 'StudyPace는 회원 관리와 목표에 맞는 학습 계획 제공을 위해 아래 정보를 수집·이용합니다.',
    sections: [
      {
        title: '1. 수집하는 정보와 이용 목적',
        items: [
          '이메일·비밀번호: 회원가입, 로그인, 이메일 인증 및 비밀번호 재설정에 이용합니다. 비밀번호 인증은 Supabase Auth에서 처리합니다.',
          '닉네임: 서비스에서 회원을 표시하는 데 이용합니다.',
          '필수 안내 동의 여부·선택 수신 동의 여부·동의 시각: 동의 내역 확인과 선택한 설정 반영에 이용합니다.',
          '서비스 이용 중 입력·생성되는 목표, 목표 기한, 주간 가용 시간, 학습 계획, 학습 실행 기록 및 직접 작성한 메모: 계획 생성·저장, 진행 상황 조회와 학습 통계 제공에 이용합니다.',
        ],
      },
      {
        title: '2. 보유 및 이용 기간',
        paragraphs: [
          '회원정보와 학습 관련 정보는 회원으로 서비스를 이용하는 동안 보관합니다. 회원탈퇴 시 계정을 삭제하고 계정에 연결된 학습 데이터를 삭제합니다.',
          '탈퇴 프로필은 일반 서비스 데이터와 분리하여 탈퇴일부터 1년간 보관한 뒤 삭제합니다. 비밀번호를 탈퇴 프로필에 저장하지 않습니다.',
        ],
      },
      {
        title: '3. 동의를 거부할 권리',
        paragraphs: [
          '개인정보 수집·이용 동의를 거부할 수 있습니다. 다만 위 정보는 회원 서비스 제공에 필요한 항목이므로 동의하지 않으면 회원가입을 진행할 수 없습니다.',
          '선택 항목인 학습 알림 수신에 동의하지 않아도 회원가입할 수 있습니다.',
        ],
      },
      {
        title: '4. 입력 시 유의사항',
        paragraphs: [
          '목표나 메모에는 주민등록번호, 결제정보, 비밀번호, 건강정보 또는 다른 사람의 개인정보 등 학습 계획에 필요하지 않은 정보를 입력하지 마세요.',
          '외부 캘린더 연결 등 추가 권한이 필요한 기능은 연결 단계에서 제공되는 접근 범위와 안내를 확인해 주세요.',
        ],
      },
    ],
    acknowledgement: '수집 항목·목적·보유 기간과 동의 거부 시 제한을 확인했습니다.',
    action: '동의하고 닫기',
  },
  ai: {
    title: 'AI 생성 콘텐츠 이용 안내',
    label: '필수',
    summary: 'AI가 활용되는 범위와 결과 확인 시 주의사항을 안내합니다.',
    introduction: 'StudyPace는 목표를 학습 단위로 나누거나 추천 설명을 만드는 과정 등에 생성형 AI를 활용합니다.',
    sections: [
      {
        title: '1. AI를 활용하는 방식',
        paragraphs: [
          '목표와 가용 시간 등을 바탕으로 학습 단위, 예상 학습 시간과 추천 설명을 제안합니다. 일정 배치와 규칙 검사는 별도의 계산 로직도 함께 사용하므로 모든 결과가 AI로 생성되는 것은 아닙니다.',
          'AI 요청이 실패하거나 AI를 사용할 수 없으면 미리 준비한 규칙이나 템플릿으로 결과를 제공할 수 있습니다.',
        ],
      },
      {
        title: '2. AI 처리에 사용하는 입력',
        paragraphs: [
          '학습 계획 생성 시 입력한 목표와 목표 식별값, 주간 가용 시간 및 필요한 참고 정보를 외부 AI 처리 서비스에 전달하여 결과를 생성합니다.',
          '목표나 요청 내용에 비밀번호, 민감한 개인정보 또는 다른 사람의 비공개 정보를 입력하지 마세요.',
        ],
      },
      {
        title: '3. 결과의 한계',
        items: [
          '학습 내용, 난이도, 소요 시간과 추천 설명이 부정확하거나 최신 정보와 다를 수 있습니다.',
          '추천 결과는 합격, 성적 향상 또는 목표 달성을 보장하지 않습니다.',
          '시험 범위, 접수 일정과 공모전 조건 등 중요한 사항은 해당 기관의 공식 자료로 확인해 주세요.',
        ],
      },
      {
        title: '4. 확인 후 계획 확정',
        paragraphs: [
          '생성된 내용을 검토하고 본인의 상황에 맞게 조정한 후 계획을 확정해 주세요. 의료·법률·금융 등 전문적인 판단을 대신하는 용도로 사용하지 마세요.',
          '이 항목은 AI 활용과 한계를 확인하기 위한 필수 안내입니다. 확인하지 않으면 현재 회원가입을 진행할 수 없습니다.',
        ],
      },
    ],
    acknowledgement: 'AI 활용 방식과 한계를 확인하고 결과를 검토하여 이용하겠습니다.',
    action: '확인·동의하고 닫기',
  },
  marketing: {
    title: '학습 알림 수신 동의',
    label: '선택',
    summary: '마감 임박·학습 독촉 알림을 받는 것에 대한 선택 항목입니다.',
    introduction: 'StudyPace 안의 알림(머리글의 알림)과 허용한 경우 브라우저 알림으로 아래 안내를 받을지 선택할 수 있습니다.',
    sections: [
      {
        title: '1. 수신 내용과 이용 정보',
        paragraphs: [
          '관심 등록한 공모전의 마감 24시간 전 안내와 끝내지 못한 학습 블록 독촉을 받는 항목입니다. 수신 동의 여부와 알림 기록을 이용합니다.',
          '블록 시작 알림, 주간 요약, 밤사이 일정을 다시 맞춘 결과는 내 일정에 관한 안내라 이 동의와 별개로 기본 제공되며 마이페이지 알림 설정에서 끌 수 있습니다.',
          '이 동의는 광고 수신이나 제3자에 대한 개인정보 제공에 동의하는 것이 아닙니다. 지금은 이메일로 알림을 보내지 않습니다.',
        ],
      },
      {
        title: '2. 자유롭게 선택할 수 있습니다',
        paragraphs: [
          '동의하지 않아도 회원가입, 목표 설정과 학습 계획 등 기본 기능을 이용할 수 있습니다.',
          '가입 전에 체크를 해제하면 수신 미동의 상태로 가입됩니다. 개인정보 수집·이용과 AI 이용 안내의 필수 동의 여부에는 영향을 주지 않습니다.',
        ],
      },
      {
        title: '3. 이용 기간과 동의 철회',
        paragraphs: [
          '수신 동의는 마이페이지 → 알림 설정에서 항목별로 언제든 끌 수 있으며, 알림 기록은 회원탈퇴 시 삭제합니다.',
          '회원정보 자체의 보관 기간과 탈퇴 프로필 보관 기준은 개인정보 수집·이용 동의 안내를 따릅니다.',
        ],
      },
      {
        title: '4. 계정 관련 이메일과의 구분',
        paragraphs: [
          '이메일 인증과 비밀번호 재설정처럼 계정 이용에 필요한 이메일은 학습 알림 수신 선택과 별개입니다.',
        ],
      },
    ],
    acknowledgement: '선택 항목임을 확인했으며 학습 알림 수신에 동의합니다.',
    action: '수신에 동의하고 닫기',
  },
};

function ConsentRow({ kind, checked, onChange, onOpen, baseId }) {
  const content = CONTENT[kind];
  return (
    <div className={styles.row}>
      <input
        id={`${baseId}-${kind}`}
        name={kind === 'marketing' ? 'marketing' : undefined}
        type="checkbox"
        checked={checked}
        onChange={(event) => {
          if (event.target.checked) onOpen(kind);
          else onChange(false);
        }}
        aria-label={`${content.title} ${checked ? '동의 해제' : '안내 확인'}`}
        aria-describedby={`${baseId}-${kind}-summary`}
      />
      <div className={styles.rowBody}>
        <button type="button" className={styles.details} onClick={() => onOpen(kind)} aria-haspopup="dialog">
          <span className={kind === 'marketing' ? styles.optional : styles.required}>[{content.label}]</span>
          <span>{content.title}</span>
          <span className={styles.openText}>내용 보기 ›</span>
        </button>
        <p id={`${baseId}-${kind}-summary`} className={styles.summary}>{content.summary}</p>
        {checked && <span className={styles.agreed}>동의 완료 · 체크를 해제하면 취소됩니다</span>}
      </div>
    </div>
  );
}

export default function SignupConsentFields({ privacy, onPrivacyChange, aiNotice, onAiNoticeChange, marketing, onMarketingChange, disabled = false }) {
  const [active, setActive] = useState(null);
  const dialogRef = useRef(null);
  const titleRef = useRef(null);
  const bodyRef = useRef(null);
  const openerRef = useRef(null);
  const baseId = useId();
  const content = active ? CONTENT[active] : null;

  useEffect(() => {
    if (!active) return;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    if (!dialog.open) dialog.showModal();
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
    titleRef.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
      openerRef.current?.focus();
    };
  }, [active]);

  function open(kind) {
    openerRef.current = document.activeElement;
    setActive(kind);
  }

  function close() {
    setActive(null);
  }

  function agree() {
    if (active === 'privacy') onPrivacyChange(true);
    if (active === 'ai') onAiNoticeChange(true);
    if (active === 'marketing') onMarketingChange(true);
    close();
  }

  return (
    <>
      <fieldset className={`panel ${styles.fieldset}`} disabled={disabled}>
        <legend className="tiny strong">약관 및 안내 확인</legend>
        <p className={styles.description}>각 항목의 내용을 확인하고 동의해 주세요. 선택 항목은 동의하지 않아도 가입할 수 있습니다.</p>
        <ConsentRow kind="privacy" checked={privacy} onChange={onPrivacyChange} onOpen={open} baseId={baseId} />
        <ConsentRow kind="ai" checked={aiNotice} onChange={onAiNoticeChange} onOpen={open} baseId={baseId} />
        <ConsentRow kind="marketing" checked={marketing} onChange={onMarketingChange} onOpen={open} baseId={baseId} />
      </fieldset>
      <dialog
        ref={dialogRef}
        className={styles.dialog}
        aria-labelledby={`${baseId}-title`}
        aria-describedby={`${baseId}-intro`}
        onCancel={(event) => { event.preventDefault(); close(); }}
      >
        {content && (
          <div className={styles.dialogLayout}>
            <header className={styles.header}>
              <div>
                <span className={active === 'marketing' ? styles.optional : styles.required}>{content.label} 안내</span>
                <h2 id={`${baseId}-title`} ref={titleRef} tabIndex={-1}>{content.title}</h2>
              </div>
              <button type="button" className={styles.closeButton} onClick={close} aria-label="안내창 닫기">×</button>
            </header>
            <div ref={bodyRef} className={styles.body}>
              <p id={`${baseId}-intro`} className={styles.introduction}>{content.introduction}</p>
              {content.sections.map((section) => (
                <section key={section.title} className={styles.section}>
                  <h3>{section.title}</h3>
                  {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                  {section.items && <ul>{section.items.map((item) => <li key={item}>{item}</li>)}</ul>}
                </section>
              ))}
              <p className={styles.acknowledgement}>{content.acknowledgement}</p>
            </div>
            <footer className={styles.footer}>
              <p>닫기만 하면 동의 상태가 변경되지 않습니다.</p>
              <div className={styles.actions}>
                <button type="button" className={`btn ${styles.secondary}`} onClick={close}>닫기</button>
                <button type="button" className={`btn btn-primary ${styles.primary}`} onClick={agree}>{content.action}</button>
              </div>
            </footer>
          </div>
        )}
      </dialog>
    </>
  );
}
