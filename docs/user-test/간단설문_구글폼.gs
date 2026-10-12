/**
 * StudyPace 실사용자 간단 설문 — 구글 폼 자동 생성 스크립트
 *
 * 쓰는 법
 *   1. https://script.google.com → 새 프로젝트
 *   2. 기본 코드를 지우고 이 파일 내용을 전부 붙여넣기 → 저장
 *   3. 위쪽 함수 선택이 createSurvey 인지 확인 → 실행 → 권한 허용(처음 한 번)
 *   4. 아래 '실행 로그'에 나오는 두 주소
 *      - 편집 주소: 진행자만 (응답 확인 · 스프레드시트 연결)
 *      - 응답 주소: 참여자에게 보낼 링크
 *
 * 문항 번호(A1·B0·C3·D2 …)는 설문_인터뷰.md · 리포트.md 2절과 같다.
 * 이름·이메일은 받지 않는다 — P번호로만 구분한다.
 */
function createSurvey() {
  var form = FormApp.create('StudyPace 사용 테스트 설문 (3분)');
  form.setDescription(
    'StudyPace 를 써 주셔서 감사합니다. 3분이면 끝나요.\n' +
    '이름·이메일은 받지 않고, 결과는 P1·P2 처럼 번호로만 씁니다.\n' +
    '척도 문항: 1 전혀 아니다 · 2 아니다 · 3 보통 · 4 그렇다 · 5 매우 그렇다'
  );
  form.setCollectEmail(false);
  form.setProgressBar(true);
  form.setConfirmationMessage('응답해 주셔서 감사합니다! 남겨 주신 의견은 서비스 개선에 반영할게요.');

  function scale(title, help) {
    var item = form.addScaleItem()
      .setTitle(title)
      .setBounds(1, 5)
      .setLabels('전혀 아니다', '매우 그렇다')
      .setRequired(true);
    if (help) item.setHelpText(help);
    return item;
  }

  // ── 참여 동의 · 번호 ──
  form.addSectionHeaderItem()
    .setTitle('참여 동의')
    .setHelpText(
      '1. 목적: 서비스 개선과 코디세이 최종 프로젝트 결과 보고\n' +
      '2. 수집 항목: 서비스 이용 기록(목표·계획·학습 기록·알림 기록·추천 평가), 설문 응답\n' +
      '3. 이용 방법: 보고서와 발표에는 P1, P2 처럼 이름 없이 번호로만 씁니다\n' +
      '4. 보관과 삭제: 테스트 명단은 프로젝트 종료(10/20) 후 삭제합니다. 서비스 계정은 마이페이지 \'회원 탈퇴\'로 언제든 지울 수 있습니다\n' +
      '5. 참여는 자유이며 언제든 그만두실 수 있습니다'
    );
  form.addCheckboxItem()
    .setTitle('위 내용을 읽고 설문 참여에 동의합니다')
    .setChoiceValues(['동의합니다'])
    .setRequired(true);

  var pattern = FormApp.createTextValidation()
    .setHelpText('P 와 숫자로 적어 주세요 (예: P3)')
    .requireTextMatchesPattern('^[Pp][0-9]+$')
    .build();
  form.addTextItem()
    .setTitle('참여자 번호')
    .setHelpText('진행자가 알려 드린 번호 (예: P3)')
    .setValidation(pattern)
    .setRequired(true);

  // ── A. 핵심 기능 ──
  form.addSectionHeaderItem().setTitle('A. 핵심 기능');
  scale('A1. 추천된 목표가 내 관심·상황에 맞았다');
  scale('A2. 처음 만들어진 일정을 보고 바로 실행할 수 있겠다고 느꼈다');
  scale('A4. 일정이 밀렸을 때 다시 놓인 일정을 믿고 따를 수 있었다',
    '밀린 블록은 밤사이 자동으로 다시 배치돼요. 겪어 보지 않았다면 3(보통)을 골라 주세요');
  scale('A5. 지금 잘 가고 있는지 알 수 있었다', '대시보드 진도 · 주간 요약 등');

  // ── B. 알림 ──
  form.addSectionHeaderItem().setTitle('B. 알림');
  form.addMultipleChoiceItem()
    .setTitle('B0. 내 알림 강도')
    .setHelpText('마이페이지 → 알림 설정에서 확인할 수 있어요')
    .setChoiceValues(['보통', '강', '기억 안 남'])
    .setRequired(true);
  scale('B1. 알림이 공부를 시작하는 데 도움이 됐다');
  scale('B2. 알림이 부담스럽거나 귀찮았다');

  // ── C · D. 사용성 · 계속 사용 ──
  form.addSectionHeaderItem().setTitle('C · D. 사용성과 계속 사용');
  scale('C3. 쓰기 쉬웠다');
  scale('D1. 테스트가 끝나도 계속 쓸 생각이 있다');
  form.addScaleItem()
    .setTitle('D2. 비슷한 준비를 하는 친구에게 추천할 가능성')
    .setBounds(0, 10)
    .setLabels('전혀 없다', '꼭 추천한다')
    .setRequired(true);

  // ── E. 서술 (선택) ──
  form.addSectionHeaderItem().setTitle('E. 한마디 (선택)');
  form.addParagraphTextItem().setTitle('E1. 가장 좋았던 것 한 가지');
  form.addParagraphTextItem().setTitle('E2. 가장 불편했거나 이해가 안 됐던 것 한 가지');

  Logger.log('편집 주소 (진행자용): ' + form.getEditUrl());
  Logger.log('응답 주소 (참여자에게 보낼 링크): ' + form.getPublishedUrl());
}
