# nanobot + Teams (Bot Framework Relay)

이 저장소는 아래 2개 앱이 함께 동작하는 구조입니다.

1. `nanobot`  
   AI 에이전트 본체. 사용자 메시지를 처리하고 답변을 생성합니다.
2. `16.proactive-messages`  
   Bot Framework 백엔드(Teams 중계 서버). Teams에서 받은 메시지를 nanobot으로 전달하고, 필요 시 proactive 메시지를 Teams로 보냅니다.

## 전체 구조 (한눈에 보기)

```text
User
  -> Teams
  -> Azure Bot Service
  -> 16.proactive-messages (/api/messages)
  -> nanobot relay (/internal/inbound)
  -> nanobot Agent
  -> (응답) 16.proactive-messages
  -> Teams
  -> User
```

proactive(능동 메시지) 경로:

```text
nanobot Agent
  -> nanobot relay
  -> 16.proactive-messages (/internal/proactive)
  -> Teams
  -> User
```

## 폴더 구조

- `nanobot/`: nanobot 코어 코드
- `16.proactive-messages/`: Teams Bot Framework 백엔드
- `16.proactive-messages/CODE_MAP.md`: 백엔드 로직별 코드 위치
- `workspace/TEAMS_CHANNEL_ARCHITECTURE.md`: 아키텍처 설계 문서

## 빠른 시작 (로컬)

### 1) nanobot 설치

```bash
cd /Users/ahk/github_codes/nanobot
python -m pip install -e .
```

### 2) Teams 백엔드 의존성 설치

```bash
cd /Users/ahk/github_codes/nanobot/16.proactive-messages
python -m pip install -r requirements.txt
```

### 3) nanobot relay 실행

```bash
cd /Users/ahk/github_codes/nanobot
python -m nanobot relay --host 127.0.0.1 --port 18800
```

### 4) Teams Bot Framework 백엔드 실행

```bash
cd /Users/ahk/github_codes/nanobot/16.proactive-messages
export NANOBOT_INBOUND_URL=http://127.0.0.1:18800/internal/inbound
python app.py
```

### 5) 헬스체크

- `GET http://127.0.0.1:3978/healthz`
- `GET http://127.0.0.1:3978/api/messages`  
  브라우저에서는 안내문만 보입니다. 실제 메시지는 `POST /api/messages`로 들어옵니다.

## Azure/Teams 연결

Azure Bot Service에서 Messaging endpoint를 다음으로 설정합니다.

```text
https://<your-backend>/api/messages
```

`16.proactive-messages`를 Azure App Service에 배포하면 Teams 앱으로 연결할 수 있습니다.

### Azure App Service zip 배포 (16.proactive-messages)

`16.proactive-messages`를 압축해 App Service에 배포하는 경우:

1. `startup.sh` 포함해서 배포
2. App Service Startup Command 설정
   - zip 루트에 `app.py`가 바로 있으면: `bash /home/site/wwwroot/startup.sh`
   - zip 루트에 `16.proactive-messages/` 폴더가 있으면:
     `bash /home/site/wwwroot/16.proactive-messages/startup.sh`
3. `startup.sh`는 아래를 자동 수행
   - venv 생성/활성화
   - 의존성 설치
   - `gunicorn + aiohttp worker`로 `app:APP` 실행

## 필수 환경변수

### Teams 백엔드 (`16.proactive-messages/app.py`)

- `MicrosoftAppId`
- `MicrosoftAppPassword`
- `MicrosoftAppType` (권장: `SingleTenant`, 기본값 `MultiTenant`)
- `MicrosoftAppTenantId`
- `PORT` (기본값 `3978`)
- `NANOBOT_INBOUND_URL` (기본값 `http://127.0.0.1:18800/internal/inbound`)
- `NANOBOT_TIMEOUT_SEC` (기본값 `20`)
- `INTERNAL_TOKEN` (선택, 내부 API 보호)
- `REFERENCE_STORE_PATH` (기본값 `./data/conversation_references.json`)

### nanobot relay (`python -m nanobot relay`)

- `INTERNAL_TOKEN` (선택, `/internal/inbound` 인증)
- `TEAMS_INTERNAL_TOKEN` (선택, 백엔드 `/internal/proactive` 호출 인증)

같은 토큰을 양쪽에 맞춰 쓰면 가장 단순합니다.

### App Service 권장 값 예시

- `NANOBOT_INBOUND_URL=https://moai-ext.mobs.com/dt-atlassian/chat/internal/inbound`
- `INTERNAL_TOKEN=<relay와_동일한_토큰>`
- `NANOBOT_TIMEOUT_SEC=120`
- `REFERENCE_STORE_PATH=/home/data/conversation_references.json`

## 어떻게 사용하나?

1. Teams에서 사용자 메시지를 보냅니다.
2. 백엔드가 메시지를 받아 nanobot relay로 전달합니다.
3. nanobot이 답변을 생성해 반환합니다.
4. 백엔드가 Teams로 응답합니다.
5. nanobot의 cron/tool 결과는 proactive로 Teams에 푸시할 수 있습니다.

## Teams 연결 전 웹 채팅(Streamlit) 테스트

Teams 대신 브라우저 채팅 UI로 relay를 먼저 검증할 수 있습니다.

1. relay 실행

```bash
cd /Users/ahk/github_codes/nanobot
python -m nanobot relay --host 0.0.0.0 --port 18800 --inbound-timeout 120
```

2. Streamlit 실행

```bash
cd /Users/ahk/github_codes/nanobot
python -m pip install -e ".[ui]"
streamlit run streamlit_chat.py
```

3. 브라우저에서 사이드바 값을 확인

- Inbound URL: `http://127.0.0.1:18800/internal/inbound` (로컬)
- Internal Token: relay를 `INTERNAL_TOKEN`으로 띄웠다면 동일 값 입력
- Auto Poll: 켜두면 `/internal/web/poll`을 주기적으로 조회해 cron/비동기 응답을 표시

`status=accepted`가 자주 보이면 relay `--inbound-timeout` 값을 더 크게 설정하세요.

### 로컬 실행 시 NANOBOT_INBOUND_URL

로컬에서 `app.py`와 relay를 같이 실행하면 아래를 사용합니다.

```bash
NANOBOT_INBOUND_URL=http://127.0.0.1:18800/internal/inbound
```

relay가 다른 서버에 있으면 `http://<relay-ip>:18800/internal/inbound`처럼
실제 접근 가능한 주소를 사용하세요.

### SSL 오류 트러블슈팅

`[SSL: ...] record layer failure (_ssl.c:1016)`는 보통 프로토콜 불일치입니다.

- `https://`로 호출했는데 대상이 `http://`인 경우
- URL 오타(`https:...`) 또는 프록시 TLS 종료 설정 문제

로컬 테스트는 먼저 `http://127.0.0.1:18800/internal/inbound`로 확인하세요.

## 코드 읽기 시작점

- 백엔드 진입점: `16.proactive-messages/app.py`
- 백엔드 로직 맵: `16.proactive-messages/CODE_MAP.md`
- nanobot relay 서버: `nanobot/relay/server.py`
- relay CLI 커맨드: `nanobot/cli/commands.py`의 `relay`
