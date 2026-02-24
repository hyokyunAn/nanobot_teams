# Code Map

로직별 구현 위치:

1. 앱 초기화/라우팅
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py)

2. Teams 메시지 수신 -> nanobot 중계
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `messages()`
- [bots/relay_bot.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/bots/relay_bot.py): `on_message_activity()`
- [nanobot_client.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/nanobot_client.py): `NanobotClient.ask()`

3. ConversationReference 저장/조회
- [bots/relay_bot.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/bots/relay_bot.py): `_remember_reference()`
- [reference_store.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/reference_store.py)

4. Proactive 전송
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `proactive()`
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `ADAPTER.continue_conversation(...)`

5. 설정/보안
- [config.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/config.py): 환경변수 로드
- [app.py](/Users/ahk/github_codes/nanobot/16.proactive-messages/app.py): `_internal_auth_ok()`

6. nanobot 측 inbound/proactive 릴레이
- [commands.py](/Users/ahk/github_codes/nanobot/nanobot/cli/commands.py): `relay` 커맨드
- [server.py](/Users/ahk/github_codes/nanobot/nanobot/relay/server.py): `/internal/inbound` 수신, outbound proactive 전달
