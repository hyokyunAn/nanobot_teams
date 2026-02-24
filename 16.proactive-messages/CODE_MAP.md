# Code Map

로직별 구현 위치:

1. 앱 초기화/라우팅
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): 앱 초기화, Adapter 생성, 라우터 등록
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `/api/messages`(POST), `/api/messages`(GET), `/internal/proactive`(POST), `/healthz`(GET)

2. Teams 메시지 수신 -> nanobot 중계
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `messages()` (`POST /api/messages` 진입점, 수신 로그 출력)
- [bots/relay_bot.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/bots/relay_bot.py): `on_message_activity()`
- [nanobot_client.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/nanobot_client.py): `NanobotClient.ask()` (`NANOBOT_INBOUND_URL`로 POST)

3. 브라우저 접근 안내/헬스체크
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `messages_get()` (`GET /api/messages` 안내문)
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `healthz()` (`GET /healthz`)

4. ConversationReference 저장/조회
- [bots/relay_bot.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/bots/relay_bot.py): `_remember_reference()`
- [reference_store.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/reference_store.py): JSON 파일 기반 upsert/get

5. Teams 식별자 매핑
- [bots/relay_bot.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/bots/relay_bot.py): `build_chat_id()` (`tenant|conversation|user`)
- [bots/relay_bot.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/bots/relay_bot.py): `build_sender_id()` (`user_id|aad_id`)

6. Proactive 전송
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `proactive()`
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `ADAPTER.continue_conversation(...)`

7. 설정/보안
- [config.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/config.py): 환경변수 로드 (`PORT`, `NANOBOT_INBOUND_URL`, `NANOBOT_TIMEOUT_SEC`, `INTERNAL_TOKEN` 등)
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `_internal_auth_ok()`
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `on_error()` / `on_cleanup()`

8. nanobot 측 inbound/proactive 릴레이
- [commands.py](/Users/ahk/github_codes/nanobot/nanobot/cli/commands.py): `relay` 커맨드
- [server.py](/Users/ahk/github_codes/nanobot/nanobot/relay/server.py): `/internal/inbound` 수신, sync 응답/accepted 처리, Teams backend `/internal/proactive` 호출
