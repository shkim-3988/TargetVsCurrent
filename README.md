📌 TargetPriceRankerV2 — Kiwoom + Naver 목표가 기반 Upside Ranking Tool
📖 개요
TargetPriceRankerV2는

Kiwoom OpenAPI+를 통해 실시간 종목 데이터를 수집하고

Naver 금융 HTML 크롤링으로 목표주가를 가져와

상승여력(Upside) 기준으로 종목을 자동 정렬해주는 프로그램입니다.

V2 버전에서는 다음 항목이 추가되었습니다:

전일종가

거래량

거래대금

상장주식수

시가총액

🚀 주요 기능
✔ Kiwoom OpenAPI+ 실시간 TR(opt10001) 데이터 수집
현재가

전일종가

거래량

거래대금

상장주식수

시가총액

✔ Naver 금융 목표주가 멀티스레드 크롤링
BeautifulSoup 기반

10개 스레드로 빠르게 수집

✔ 상승여력 자동 계산
코드
상승여력(%) = (목표가 - 현재가) / 현재가 × 100
✔ KOSPI / KOSDAQ 자동 분리 및 정렬
KOSPI 먼저 정렬

KOSDAQ 다음 정렬

✔ PyQt5 GUI 제공
진행률 표시

실시간 테이블 업데이트

CSV 자동 저장

🛠 설치 방법
1) Python 설치
Python 3.9 ~ 3.11 권장
(3.12은 PyQt5 호환성 문제 가능)

2) 필요한 패키지 설치
프로젝트 폴더에서 아래 명령 실행:

코드
pip install -r requirements.txt
requirements.txt 내용 예시:

코드
requests
beautifulsoup4
PyQt5
🏦 Kiwoom OpenAPI+ 준비
이 프로그램은 키움증권 OpenAPI+를 사용합니다.
다른 PC에서 실행하려면 아래 준비가 필요합니다.

✔ 1) 키움증권 계좌 개설
(모의투자 계좌도 가능)

✔ 2) 영웅문 HTS 설치
https://www.kiwoom.com → 다운로드 → 영웅문4

✔ 3) Kiwoom OpenAPI+ 설치
영웅문 설치 시 자동 포함됨
(없으면 “OpenAPI+” 검색하여 설치)

✔ 4) 로그인 필수
프로그램 실행 전 반드시:

영웅문 실행

공인인증서 로그인

계좌 비밀번호 입력

▶ 실행 방법
프로젝트 폴더에서 아래 명령 실행:

코드
python TargetPriceRankerV2.py
실행 후:

자동 로그인

네이버 목표가 수집

Kiwoom TR 수집

상승여력 기준 정렬

CSV 자동 저장

📁 CSV 저장 위치
프로그램 실행 후 자동으로 아래 형식으로 저장됩니다:

코드
목표가_vs_현재가_V2_YYYYMMDD.csv
CSV에는 다음 항목이 포함됩니다:

순위

시장

종목코드

종목명

현재가

목표가

상승여력

전일종가

거래량

거래대금

상장주식수

시가총액

📌 폴더 구조 예시
코드
TargetVsCurrent/
 ├─ TargetPriceRankerV2.py
 ├─ TargetPriceRanker.py
 ├─ requirements.txt
 ├─ README.md
 └─ 기타 리소스 파일
⚠ 주의사항
반드시 Windows 환경에서만 실행 가능 (Kiwoom API 제한)

반드시 영웅문 로그인 상태여야 TR 호출 가능

네이버 크롤링은 HTML 구조 변경 시 동작이 달라질 수 있음

너무 많은 TR 요청 시 키움 API가 일시적으로 차단될 수 있음

🙋 문의 / 개선 요청
이 프로그램은 누구나 자유롭게 수정·확장할 수 있습니다.
개선 아이디어나 버그 제보는 Issue로 등록해주세요.
