# Teams Integration Architecture (Azure Bot Framework Relay)

## 1) 목표

- Teams 앱은 Bot Framework 기반 Azure App(백엔드)로 배포한다.
- Azure 백엔드는 비즈니스 로직을 최소화하고, nanobot과 Teams 사이의 중계 역할만 수행한다.
- 일반 대화와 능동 메시지(proactive)를 모두 지원한다.

## 2) 최종 구조

`사용자 <-> Teams <-> Azure Bot Service <-> Azure Bot Backend(App Service) <-> nanobot`

핵심 원칙:

- Teams/Bot Framework 관련 책임은 모두 Azure Bot Backend에 둔다.
- nanobot은 LLM/툴 실행과 응답 생성에 집중한다.
- Azure Bot Backend는 ConversationReference 저장/조회 + 전달만 담당한다.

## 3) 컴포넌트 책임 분리

### Azure Bot Backend (Bot Framework 코드, Azure 배포)

- `POST /api/messages`로 Teams activity 수신.
- 매 턴 `ConversationReference` upsert.
- inbound 메시지를 nanobot으로 전달.
- nanobot 응답을 Teams로 반환:
  - 빠른 응답: in-turn reply
  - 지연 응답: `continue_conversation()` proactive reply
- nanobot에서 오는 능동 전송 요청(`/internal/proactive`) 처리.

### nanobot

- Azure Bot Backend에서 전달된 사용자 메시지를 처리.
- 결과 텍스트를 Azure Bot Backend로 반환/전송.
- cron/tool/system 이벤트 결과를 proactive 요청으로 Azure Bot Backend에 전달.

## 4) 메시지 흐름

### 4.1 일반 대화 (권장: sync + timeout fallback)

1. User -> Teams 메시지 전송.
2. Azure Bot Backend `/api/messages` 수신.
3. Backend가 ConversationReference 저장/갱신.
4. Backend -> nanobot `inbound` 요청.
5. nanobot이 제한 시간 내 응답하면 Backend가 즉시 `send_activity`.
6. 제한 시간 초과면 Backend가 "처리 중" 안내를 보낸 뒤, 최종 응답은 proactive로 전송.

### 4.2 능동 메시지

1. nanobot 내부 작업 완료(cron/tool/system event).
2. nanobot -> Backend `/internal/proactive` 요청(`chat_id`, `text`).
3. Backend가 reference 조회.
4. Backend가 `continue_conversation()`으로 Teams 전송.

## 5) 상태 저장 설계 (Backend 필수)

Teams proactive는 reference 없이는 불가하므로 Backend가 영속 저장해야 한다.

- key(권장): `tenant_id|conversation_id|user_id` (`chat_id`)
- 저장 필드(최소):
  - `chat_id` (PK)
  - `service_url`
  - `channel_id` (`msteams`)
  - `conversation.id`
  - `bot.id`
  - `user.id`
  - `tenant_id`
  - `updated_at`

저장소:

- MVP: SQLite/파일
- 운영: Redis 또는 Cosmos DB

## 6) nanobot <-> Backend 내부 API 계약

### 6.1 Backend -> nanobot (inbound)

`POST /internal/inbound`

```json
{
  "request_id": "req_123",
  "chat_id": "tenant|conversation|user",
  "sender_id": "aad_user_id",
  "content": "사용자 메시지",
  "metadata": {
    "channel": "teams",
    "message_id": "activity_id",
    "tenant_id": "xxx",
    "conversation_id": "yyy",
    "user_id": "zzz"
  }
}
```

성공 응답(빠른 응답):

```json
{
  "status": "ok",
  "content": "nanobot 응답"
}
```

지연 처리 응답:

```json
{
  "status": "accepted",
  "request_id": "req_123"
}
```

### 6.2 nanobot -> Backend (proactive/outbound)

`POST /internal/proactive`

```json
{
  "request_id": "req_123",
  "chat_id": "tenant|conversation|user",
  "content": "최종 응답 또는 능동 알림",
  "idempotency_key": "msg_123"
}
```

## 7) 장애/지연 처리 정책

- Backend -> nanobot 호출 타임아웃: 예) 8초
- 타임아웃 시 사용자에게 즉시 안내 메시지 전송
- 최종 응답은 proactive 경로로 후속 전달
- 중복 방지:
  - `request_id`, `idempotency_key` 기준 dedupe

## 8) 보안 정책

- `internal` API는 외부 비공개(VNet/Private Endpoint/IP 제한)
- 서비스 간 인증: HMAC 또는 JWT(m2m)
- 서명 검증 실패/리플레이 요청 차단
- 민감정보(App Password, signing key)는 Key Vault/환경변수로 관리

## 9) 구현 우선순위 (코딩 착수용)

1. Azure Bot Backend 기본 골격
   - `/api/messages`
   - `ConversationReference` 저장소
2. nanobot inbound API 연결
   - Backend -> nanobot 호출
   - sync 응답 path
3. proactive API 연결
   - nanobot -> Backend `/internal/proactive`
   - `continue_conversation()` 전송
4. timeout fallback + dedupe
5. 운영 저장소/보안 적용

## 10) 완료 기준 (DoD)

- Teams에서 사용자 질의 시 nanobot 응답이 정상 도달한다.
- nanobot cron/tool 결과가 Teams로 proactive 전송된다.
- Backend 재시작 후에도 기존 사용자에게 proactive 가능하다.
- request 단위 추적 로그(`request_id`, `chat_id`, `activity_id`)가 남는다.
