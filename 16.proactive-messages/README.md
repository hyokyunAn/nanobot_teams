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
- `MicrosoftAppType` (default: `MultiTenant`)
- `MicrosoftAppTenantId`
- `PORT` (default: `3978`)
- `NANOBOT_INBOUND_URL` (default: `http://127.0.0.1:18800/internal/inbound`)
- `NANOBOT_TIMEOUT_SEC` (default: `20`)
- `INTERNAL_TOKEN` (optional)
  - 설정 시, 백엔드 -> nanobot 호출 헤더(`x-internal-token`)에 사용
  - 동시에 `/internal/proactive` 인증에도 사용
- `REFERENCE_STORE_PATH` (default: `./data/conversation_references.json`)

## Run

```bash
cd /Users/ahk/github_codes/nanobot/16.proactive-messages
pip install -r requirements.txt
python app.py
```

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
- 브라우저 확인:
  - `https://<your-backend>/healthz`
  - `https://<your-backend>/api/messages` (안내문 반환)

4. Teams에서 테스트

- 일반 대화: Teams -> backend -> nanobot relay
- 능동 메시지: nanobot relay -> backend `/internal/proactive` -> Teams
