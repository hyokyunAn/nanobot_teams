# Teams Relay Backend (Bot Framework)

Azure에 배포할 Bot Framework 백엔드입니다.  
역할은 Teams 메시지를 받아 nanobot으로 전달하고, 필요 시 proactive로 Teams에 전송하는 중계자입니다.

## Endpoints

- `POST /api/messages`
  - Bot Framework 채널(Teams/Azure Bot Service)에서 호출하는 메인 엔드포인트
  - 호출이 들어오면 서버 콘솔에 수신 로그를 출력함
- `GET /api/messages`
  - 브라우저 확인용 안내 메시지 반환 (`POST only`)
- `POST /internal/proactive`
  - nanobot -> 백엔드 proactive 전송용 내부 엔드포인트
- `GET /healthz`
  - 헬스체크

## Environment

- `MicrosoftAppId`
- `MicrosoftAppPassword`
- `MicrosoftAppType` (recommended: `SingleTenant`, default: `MultiTenant`)
- `MicrosoftAppTenantId`
- `PORT` (default: `3978`)
- `NANOBOT_INBOUND_URL` (default: `http://127.0.0.1:18800/internal/inbound`)
- `NANOBOT_TIMEOUT_SEC` (default: `20`)
- `INTERNAL_TOKEN` (optional)
  - 설정 시, 백엔드 -> nanobot 호출 헤더(`x-internal-token`)에 사용
  - 동시에 `/internal/proactive` 인증에도 사용
- `REFERENCE_STORE_PATH` (default: `./data/conversation_references.json`)

## Run

로컬 실행:

```bash
cd /Users/ahk/github_codes/nanobot/16.proactive-messages
pip install -r requirements.txt
python app.py
```

로컬에서 relay와 연결할 때:

```bash
export NANOBOT_INBOUND_URL=http://127.0.0.1:18800/internal/inbound
```

## Azure App Service zip deploy

`startup.sh`를 사용하면 다음을 자동 수행합니다.

- virtualenv 생성/활성화
- 의존성 설치
- `gunicorn app:APP --worker-class aiohttp.GunicornWebWorker` 실행

Startup Command:

- zip 루트가 `16.proactive-messages` 자체일 때:
  `bash /home/site/wwwroot/startup.sh`
- zip 루트가 저장소 루트일 때:
  `bash /home/site/wwwroot/16.proactive-messages/startup.sh`

필수 App Service 환경변수:

- `MicrosoftAppId`
- `MicrosoftAppPassword`
- `MicrosoftAppType=SingleTenant`
- `MicrosoftAppTenantId`
- `NANOBOT_INBOUND_URL=https://moai-ext.mobs.com/dt-atlassian/chat/internal/inbound`
- `INTERNAL_TOKEN=<relay와 동일 토큰>`

권장:

- `NANOBOT_TIMEOUT_SEC=120`
- `REFERENCE_STORE_PATH=/home/data/conversation_references.json`

## Pipeline Run Order

1. nanobot relay 실행 (`/internal/inbound` 제공)

```bash
cd /Users/ahk/github_codes/nanobot
python -m nanobot relay --host 127.0.0.1 --port 18800
```

2. Bot Framework 백엔드 실행

```bash
cd /Users/ahk/github_codes/nanobot/16.proactive-messages
export NANOBOT_INBOUND_URL=http://127.0.0.1:18800/internal/inbound
python app.py
```

3. Azure Bot Service 설정

- Messaging endpoint: `https://<your-backend>/api/messages`
- Channels: Microsoft Teams 활성화
- 브라우저 확인:
  - `https://<your-backend>/healthz`
  - `https://<your-backend>/api/messages` (안내문 반환)

4. Teams에서 테스트

- 일반 대화: Teams -> backend -> nanobot relay
- 능동 메시지: nanobot relay -> backend `/internal/proactive` -> Teams

## Teams app 연결

- Teams 앱 매니페스트의 `botId`를 `MicrosoftAppId`와 동일하게 설정
- 앱 업로드 후 개인/팀 스코프에서 설치

## Troubleshooting

에러: `[SSL: ...] record layer failure (_ssl.c:1016)`

원인(대부분): HTTPS/HTTP 프로토콜 불일치

- `NANOBOT_INBOUND_URL`을 HTTPS로 설정했는데 실제 relay는 HTTP만 듣는 경우
- 프록시 TLS 종료/포워딩 설정 불일치

로컬 테스트는 아래 URL부터 확인하세요.

```bash
http://127.0.0.1:18800/internal/inbound
```
