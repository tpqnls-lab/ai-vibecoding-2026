### ai-vibecoding-2026

바이브코딩 리포지토리

## Chapter 1

AI에게 코딩을 시키자, 제대로!

### 개념

코딩을 직접하지는 말 것. AI와 협업해서 새로운 프로그램을 만들자

#### 기존 개발 방법

요구사항 분석 -> 설계(DB/UI 포함) -> 구현/디버깅 -> 테스트 -> 배포 -> 유지보수

#### 바이브코딩 방식

요구사항정의(PRD) -> AI 코드 생성/디버깅, 테스트 -> **사람 검증**, 수정 요청, 직접 수정 -> 배포(AI가능) -> AI 유지보수

#### 핵심 포인트

- AI - 주니어/시니어 개발
- 사람 - PM + 리뷰어

### 바이브코딩 개발환경

- VS Code, VS code Insider, Android Studio, ....

#### VS Code

- 채팅 창 - 안씀
- 확장 - 패키지 - Codex, Claude Code for VS Code, Gemini Code Assist

#### Codex

- 설치 후 확장 아이콘 아래, Codex 아이콘 생성

![](https://github.com/hugoMGSung/ai-vibecoding-2026/raw/main/assets/20260917_170818_image.png)

- 로그인 - 웹 브라우저 연결
- 설정화면 설정 필요

![](https://github.com/hugoMGSung/ai-vibecoding-2026/raw/main/assets/20260917_171229_image.png)

- 추가파일 Codex-*-SandBox-.exe 설치

![](https://github.com/hugoMGSung/ai-vibecoding-2026/raw/main/assets/20260917_171318_image.png)

- 최종 화면
- 채팅 창 명령 / 여러 LLM에 전달 할 명령어 리스트

#### 바이브코딩 맛보기

![](https://github.com/hugoMGSung/ai-vibecoding-2026/raw/main/assets/20260917_172319_image.png)

- 제로샷 프롬프트 요청

![](https://github.com/hugoMGSung/ai-vibecoding-2026/raw/main/assets/20260917_172409_image.png)

- 결과 메시지 화면
- 소스

#### CLI Codex

- 파워쉘, 콘솔 창에서 명렁어로 수행하는 Codex

### 주식 자동매매 개발환경

토스증권 OpenAPI

- https://corp.tossinvest.com/ko/open-api
- 토스앱 모바일 설치 가입
- 토스증권 사용 설정
- 토스증권 PC 웹사이트 동작
- 사용중인 아이피를 토스증권 PC 등록
- OpenAPI Key 발급 - ClientID, Client Secret 문자열 보관

#### API 신청

- https://corp.tossinvest.com/ko/open-api
- PC에서 투자하기 클릭
- 토스앱 모바일로 로그인 인증
- 오른쪽 하단 기어모양 아이콘(설정)


![](https://github.com/hugoMGSung/ai-vibecoding-2026/raw/main/assets/20260921_170830_image.png)


Client Id, Client Secret, IP 추가
cmd > ipconfig로 보인 아이피 확인 후 추가

## 주식 자동매매 파이썬 프로그램 분석

- `__init__.py` - 일반적으로 파일만 생성. 소스코드 x 프로젝트 폴더가 pip로 설치할 수 있는 패키지화
- `__main__.py` - 파이썬으로 실행될 때 가장 먼저 실행되는 메인 함수 파일
  -`__pycache__` - 미리 만들어놓은 파이썬 실행 파일(캐시)
  - tests - 소스코드 테스트 실행을 위한 폴더
- .env.example - 환결설정 예제파일 .example을 지우거나 복사 후 사용
      .env는 GitHub에 업로드 방지위해 .gitignore에 제외파일로 등록
- requirements.txt - 파이썬 개발환경 패키지 설치리스트 파일
    - `pip install -r requirements.txt`로 전부 설치
    