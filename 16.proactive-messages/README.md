# Teams Relay Backend (Bot Framework)

Azure에 배포할 Bot Framework 백엔드입니다.  
역할은 Teams 메시지를 받아 nanobot에 전달하고, 필요 시 proactive로 Teams에 전송하는 중계자입니다.

## Endpoints

- `POST /api/messages`
- `POST /internal/proactive`
- `GET /healthz`

## Environment

- `MicrosoftAppId`
- `MicrosoftAppPassword`
- `MicrosoftAppType` (default: `MultiTenant`)
- `MicrosoftAppTenantId`
- `PORT` (default: `3978`)
- `NANOBOT_INBOUND_URL` (default: `http://127.0.0.1:18800/internal/inbound`)
- `NANOBOT_TIMEOUT_SEC` (default: `8`)
- `INTERNAL_TOKEN` (optional)
- `REFERENCE_STORE_PATH` (default: `./data/conversation_references.json`)

## Run

```bash
pip install -r requirements.txt
python app.py
```

