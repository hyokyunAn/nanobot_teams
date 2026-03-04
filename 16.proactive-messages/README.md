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

`.env` 파일(권장) 또는 App Service 환경변수로 설정합니다.

- `MicrosoftAppId`
- `MicrosoftAppPassword`
- `MicrosoftAppType` (recommended: `SingleTenant`, default: `MultiTenant`)
- `MicrosoftAppTenantId`
- `PORT` (default: `3978`)
- `APP_BIND_HOST` (optional)
- `GUNICORN_BIND` (default: `:${PORT}`)
- `NANOBOT_INBOUND_URL` (required)
- `NANOBOT_INBOUND_HOST` (optional, host header override)
- `NANOBOT_TIMEOUT_SEC` (default: `20`)
- `NANOBOT_VERIFY_SSL` (default: `true`)
- `INTERNAL_TOKEN` (optional)
  - 설정 시, 백엔드 -> nanobot 호출 헤더(`x-internal-token`)에 사용
  - 동시에 `/internal/proactive` 인증에도 사용
- `REFERENCE_STORE_PATH` (default: `./data/conversation_references.json`)

`.env` 템플릿:

```bash
cp .env.example .env
```

선택: 다른 파일 경로를 쓰려면 `NANOBOT_ENV_FILE=/path/to/env`를 설정할 수 있습니다.

## Run

로컬 실행:

```bash
cd /Users/ahk/github_codes/nanobot/16.proactive-messages
pip install -r requirements.txt
cp .env.example .env   # 값 입력
python app.py
```

로컬에서 relay와 연결할 때:

```bash
# set NANOBOT_INBOUND_URL in .env
```

## Azure App Service zip deploy

`startup.sh`를 사용하면 다음을 자동 수행합니다.

- virtualenv 생성/활성화
- 의존성 설치
- `gunicorn app:APP --worker-class aiohttp.worker.GunicornWebWorker` 실행

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
- `NANOBOT_INBOUND_URL=<relay inbound endpoint>`
- `NANOBOT_INBOUND_HOST=<expected host header>`
- `INTERNAL_TOKEN=<relay와 동일 토큰>`

권장:

- `NANOBOT_TIMEOUT_SEC=120`
- `NANOBOT_VERIFY_SSL=false` (TLS 검증 이슈가 있으면)
- `REFERENCE_STORE_PATH=/home/data/conversation_references.json`

DNS/프록시 예시:

- `NANOBOT_INBOUND_HOST` 값으로 라우팅
- relay inbound 경로(`/internal/inbound`, `/healthz`)가 백엔드에서 접근 가능하도록 프록시

## Pipeline Run Order

1. nanobot relay 실행 (`/internal/inbound` 제공)

```bash
cd /Users/ahk/github_codes/nanobot
python -m nanobot relay --host "${RELAY_BIND_HOST}" --port "${RELAY_BIND_PORT}"
```

2. Bot Framework 백엔드 실행

```bash
cd /Users/ahk/github_codes/nanobot/16.proactive-messages
# .env에 값 입력 후 실행
python app.py
```

3. Azure Bot Service 설정

- Messaging endpoint: `${APP_BASE_URL}/api/messages`
- Channels: Microsoft Teams 활성화
- 브라우저 확인:
  - `${APP_BASE_URL}/healthz`
  - `${APP_BASE_URL}/api/messages` (안내문 반환)

4. Teams에서 테스트

- 일반 대화: Teams -> backend -> nanobot relay
- 능동 메시지: nanobot relay -> backend `/internal/proactive` -> Teams

## Teams app 연결

- Teams 앱 매니페스트의 `botId`를 `MicrosoftAppId`와 동일하게 설정
- 앱 업로드 후 개인/팀 스코프에서 설치

## Troubleshooting

에러: `[SSL: ...] record layer failure (_ssl.c:1016)`

원인(대부분): HTTPS/HTTP 프로토콜 불일치

- TLS 엔드포인트로 호출했는데 relay가 평문 HTTP로 동작하는 경우
- 프록시 TLS 종료/포워딩 설정 불일치
