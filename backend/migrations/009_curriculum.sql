-- 009 — 표준 커리큘럼 (담당 C, FR-PLAN-02 학습 분해 에이전트의 search_curriculum · estimate_effort 근거)
--
-- 에이전트는 여기 있는 출제 범위 "안에서" 학습 단위를 만든다. 여기 없는 내용을 넣으면 그 단위를 '추정'으로 표시한다.
-- goal_id 는 목표 카탈로그(services/goal_catalog.py, 담당 B)와 같은 값을 쓴다.
--
--   subject           과목·장 (예: SQL 활용)
--   topic             세부 항목 — 학습 단위 후보
--   standard_minutes  한 번 앉아서 공부할 권장 시간(30~120분). 팀 추정치다 — 공식 수치가 아니다
--   source            어디서 가져온 범위인지
--   verified          팀이 공식 출제기준 원문과 한 줄씩 대조했는가. 대조 전에는 false
--
-- 범위를 고칠 때는 이 파일을 고치지 말고 다음 번호 마이그레이션으로 update/insert 한다.

create table if not exists public.curriculum_units (
    id                bigint generated always as identity primary key,
    goal_id           text not null,
    goal_title        text not null,
    position          int  not null,
    subject           text not null,
    topic             text not null,
    standard_minutes  int  not null check (standard_minutes between 30 and 120),
    is_review         boolean not null default false,   -- 기출·복습 단위
    source            text not null,
    source_url        text,
    verified          boolean not null default false,
    updated_at        timestamptz not null default now(),
    unique (goal_id, position)
);

-- (goal_id, position) 조회는 unique 제약의 인덱스가 맡는다

-- 공개 정보(시험 범위)라 누구나 읽을 수 있다. 쓰기는 마이그레이션으로만
alter table public.curriculum_units enable row level security;
create policy "anyone can read curriculum"
    on public.curriculum_units for select
    using (true);

-- ── 정보처리기사 필기 ─────────────────────────────────────
insert into public.curriculum_units (goal_id, goal_title, position, subject, topic, standard_minutes, is_review, source, source_url) values
('cert-info-eng', '정보처리기사 필기',  1, '1과목 소프트웨어 설계', '요구사항 확인', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  2, '1과목 소프트웨어 설계', '화면 설계', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  3, '1과목 소프트웨어 설계', '애플리케이션 설계', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  4, '1과목 소프트웨어 설계', '인터페이스 설계', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  5, '2과목 소프트웨어 개발', '데이터 입출력 구현', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  6, '2과목 소프트웨어 개발', '통합 구현', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  7, '2과목 소프트웨어 개발', '제품소프트웨어 패키징', 60, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  8, '2과목 소프트웨어 개발', '애플리케이션 테스트 관리', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기',  9, '2과목 소프트웨어 개발', '인터페이스 구현', 60, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 10, '3과목 데이터베이스 구축', 'SQL 응용', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 11, '3과목 데이터베이스 구축', 'SQL 활용', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 12, '3과목 데이터베이스 구축', '논리 데이터베이스 설계', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 13, '3과목 데이터베이스 구축', '물리 데이터베이스 설계', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 14, '3과목 데이터베이스 구축', '데이터 전환', 60, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 15, '4과목 프로그래밍 언어 활용', '서버 프로그램 구현', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 16, '4과목 프로그래밍 언어 활용', '프로그래밍 언어 활용', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 17, '4과목 프로그래밍 언어 활용', '응용 SW 기초 기술 활용', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 18, '5과목 정보시스템 구축관리', '소프트웨어 개발 방법론 활용', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 19, '5과목 정보시스템 구축관리', 'IT 프로젝트 정보시스템 구축 관리', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 20, '5과목 정보시스템 구축관리', '소프트웨어 개발 보안 구축', 120, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 21, '5과목 정보시스템 구축관리', '시스템 보안 구축', 90, false, 'Q-Net 정보처리기사 필기 출제기준 — 과목·주요항목 요약', 'https://www.q-net.or.kr'),
('cert-info-eng', '정보처리기사 필기', 22, '기출·복습', '기출문제 풀이 1회차', 120, true, '팀 권장 학습 순서', null),
('cert-info-eng', '정보처리기사 필기', 23, '기출·복습', '기출문제 풀이 2회차', 120, true, '팀 권장 학습 순서', null),
('cert-info-eng', '정보처리기사 필기', 24, '기출·복습', '오답 정리 및 약점 복습', 90, true, '팀 권장 학습 순서', null);

-- ── SQLD ──────────────────────────────────────────────
insert into public.curriculum_units (goal_id, goal_title, position, subject, topic, standard_minutes, is_review, source, source_url) values
('cert-sqld', 'SQLD (SQL 개발자)',  1, '데이터 모델링의 이해', '데이터 모델의 이해', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  2, '데이터 모델링의 이해', '엔터티', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  3, '데이터 모델링의 이해', '속성', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  4, '데이터 모델링의 이해', '관계', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  5, '데이터 모델링의 이해', '식별자', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  6, '데이터 모델과 SQL', '정규화', 90, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  7, '데이터 모델과 SQL', '관계와 조인의 이해', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  8, '데이터 모델과 SQL', '모델이 표현하는 트랜잭션의 이해', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)',  9, '데이터 모델과 SQL', 'Null 속성의 이해', 30, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 10, '데이터 모델과 SQL', '본질식별자와 인조식별자', 30, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 11, 'SQL 기본', '관계형 데이터베이스 개요', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 12, 'SQL 기본', 'SELECT 문', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 13, 'SQL 기본', '함수', 90, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 14, 'SQL 기본', 'WHERE 절', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 15, 'SQL 기본', 'GROUP BY 절과 HAVING 절', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 16, 'SQL 기본', 'ORDER BY 절', 30, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 17, 'SQL 기본', '조인', 90, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 18, 'SQL 기본', '표준 조인', 90, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 19, 'SQL 활용', '서브쿼리', 90, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 20, 'SQL 활용', '집합 연산자', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 21, 'SQL 활용', '그룹 함수', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 22, 'SQL 활용', '윈도우 함수', 90, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 23, 'SQL 활용', 'Top N 쿼리', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 24, 'SQL 활용', '계층형 질의와 셀프 조인', 90, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 25, 'SQL 활용', 'PIVOT 절과 UNPIVOT 절', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 26, 'SQL 활용', '정규 표현식', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 27, '관리 구문', 'DML', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 28, '관리 구문', 'TCL', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 29, '관리 구문', 'DDL', 60, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 30, '관리 구문', 'DCL', 30, false, '한국데이터산업진흥원 SQLD 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-sqld', 'SQLD (SQL 개발자)', 31, '기출·복습', '기출문제 풀이 1회차', 90, true, '팀 권장 학습 순서', null),
('cert-sqld', 'SQLD (SQL 개발자)', 32, '기출·복습', '기출문제 풀이 2회차', 90, true, '팀 권장 학습 순서', null),
('cert-sqld', 'SQLD (SQL 개발자)', 33, '기출·복습', '오답 정리 및 약점 복습', 60, true, '팀 권장 학습 순서', null);

-- ── ADsP ──────────────────────────────────────────────
insert into public.curriculum_units (goal_id, goal_title, position, subject, topic, standard_minutes, is_review, source, source_url) values
('cert-adsp', 'ADsP (데이터분석 준전문가)',  1, '1과목 데이터 이해', '데이터의 이해', 60, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  2, '1과목 데이터 이해', '데이터의 가치와 미래', 60, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  3, '1과목 데이터 이해', '가치 창조를 위한 데이터 사이언스와 전략 인재', 60, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  4, '2과목 데이터 분석 기획', '데이터 분석 기획의 이해', 90, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  5, '2과목 데이터 분석 기획', '분석 마스터 플랜', 90, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  6, '3과목 데이터 분석', '데이터 분석 개요', 60, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  7, '3과목 데이터 분석', 'R 프로그래밍 기초', 120, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  8, '3과목 데이터 분석', '데이터 마트', 90, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)',  9, '3과목 데이터 분석', '통계 분석', 120, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)', 10, '3과목 데이터 분석', '정형 데이터 마이닝', 120, false, '한국데이터산업진흥원 ADsP 시험 과목 — 과목·주요항목 요약', 'https://www.dataq.or.kr'),
('cert-adsp', 'ADsP (데이터분석 준전문가)', 11, '기출·복습', '기출문제 풀이 1회차', 90, true, '팀 권장 학습 순서', null),
('cert-adsp', 'ADsP (데이터분석 준전문가)', 12, '기출·복습', '기출문제 풀이 2회차', 90, true, '팀 권장 학습 순서', null),
('cert-adsp', 'ADsP (데이터분석 준전문가)', 13, '기출·복습', '오답 정리 및 약점 복습', 60, true, '팀 권장 학습 순서', null);
