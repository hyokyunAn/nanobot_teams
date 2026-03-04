# MCP Servers

이 폴더에는 nanobot에 연결할 MCP 서버 스크립트가 있습니다.

## 1) Confluence Data Center MCP

- 서버 파일: `workspace/mcp/atlassian_confluence_mcp.py`
- 실행 스크립트: `workspace/mcp/run-atlassian-mcp.sh`

### 환경변수

```bash
export CONFLUENCE_BASE_URL="<CONFLUENCE_BASE_URL>"
export CONFLUENCE_BEARER_TOKEN="your_pat_here"
```

레거시 호환:

```bash
export CONFLUENCE_PAT="your_pat_here"
```

선택 옵션:

```bash
export CONFLUENCE_TIMEOUT_SECONDS="30"
export CONFLUENCE_VERIFY_SSL="true"
```

### 실행

```bash
./workspace/mcp/run-atlassian-mcp.sh
```

또는:

```bash
python workspace/mcp/atlassian_confluence_mcp.py
```

### 제공 기능 (tool)

- 페이지 읽기: `get_page`
- 페이지 업데이트: `update_page`
- 새 글 쓰기: `create_page`
- 하위 페이지 탐색: `list_child_pages`
- 댓글 읽기: `list_page_comments`
- 댓글 쓰기: `add_page_comment`
- 그 외: `health`, `list_spaces`, `search_pages`

nanobot 연결 후 실제 노출 이름은 `mcp_atlassian_<tool>` 입니다.

## 2) DS QA Agent MCP

- 서버 파일: `workspace/mcp/ds_qa_agent_mcp.py`
- 실행 스크립트: `workspace/mcp/run-ds-qa-mcp.sh`

### 동작 방식

- 프롬프트 페이지를 지침으로 사용
- DB 페이지 + 하위 페이지 전체를 지식베이스로 인덱싱
- 질문 시 관련 페이지를 랭킹하여 근거 + 답변 초안 반환

### 기본 환경변수

```bash
export CONFLUENCE_BASE_URL="<CONFLUENCE_BASE_URL>"
export CONFLUENCE_BEARER_TOKEN="your_pat_here"
export DS_QA_PROMPT_PAGE_URL="<DS_QA_PROMPT_PAGE_URL>"
export DS_QA_DB_PAGE_URL="<DS_QA_DB_PAGE_URL>"
```

ID를 직접 지정하고 싶으면:

```bash
export DS_QA_PROMPT_PAGE_ID="133776732"
export DS_QA_DB_PAGE_ID="133776732"
```

선택 옵션:

```bash
export DS_QA_CACHE_TTL_SECONDS="300"
export DS_QA_MAX_PAGES="300"
```

### 실행

```bash
./workspace/mcp/run-ds-qa-mcp.sh
```

또는:

```bash
python workspace/mcp/ds_qa_agent_mcp.py
```

### 제공 기능 (tool)

- 상태 확인: `health`
- 인덱스 강제 갱신: `refresh_index`
- 인덱싱된 DB 페이지 목록: `list_db_pages`
- 질의응답: `ask_data_science_qa` (우선), `ask_ds_qa`

nanobot 연결 후 실제 노출 이름은 `mcp_dsqa_<tool>` 입니다.

## 3) Jira Data Center MCP

- 서버 파일: `workspace/mcp/jira_mcp.py`
- 실행 스크립트: `workspace/mcp/run-jira-mcp.sh`

### 기본 환경변수

```bash
export JIRA_BASE_URL="<JIRA_BASE_URL>"
export JIRA_BEARER_TOKEN="your_pat_here"
```

레거시 호환:

```bash
export JIRA_PAT="your_pat_here"
```

선택 옵션:

```bash
export JIRA_TIMEOUT_SECONDS="30"
export JIRA_VERIFY_SSL="true"
```

### 실행

```bash
./workspace/mcp/run-jira-mcp.sh
```

또는:

```bash
python workspace/mcp/jira_mcp.py
```

### 제공 기능 (tool)

- 티켓 읽기: `get_issue`
- 티켓 생성: `create_issue`
- 티켓 수정(필드): `update_issue`
- 티켓 상태 변경: `transition_issue`
- 추가 기능: `search_issues`, `list_transitions`, `add_comment`, `health`

nanobot 연결 후 실제 노출 이름은 `mcp_jira_<tool>` 입니다.

## 4) nanobot 연결 (`~/.nanobot/config.json`)

아래 `tools.mcpServers` 항목을 추가/병합하세요.

```json
{
  "tools": {
    "mcpServers": {
      "atlassian": {
        "command": "python",
        "args": ["/Users/ahk/github_codes/nanobot/workspace/mcp/atlassian_confluence_mcp.py"],
        "env": {
          "CONFLUENCE_BASE_URL": "<CONFLUENCE_BASE_URL>",
          "CONFLUENCE_BEARER_TOKEN": "your_pat_here"
        }
      },
      "dsqa": {
        "command": "python",
        "args": ["/Users/ahk/github_codes/nanobot/workspace/mcp/ds_qa_agent_mcp.py"],
        "env": {
          "CONFLUENCE_BASE_URL": "<CONFLUENCE_BASE_URL>",
          "CONFLUENCE_BEARER_TOKEN": "your_pat_here",
          "DS_QA_PROMPT_PAGE_URL": "<DS_QA_PROMPT_PAGE_URL>",
          "DS_QA_DB_PAGE_URL": "<DS_QA_DB_PAGE_URL>"
        }
      },
      "jira": {
        "command": "python",
        "args": ["/Users/ahk/github_codes/nanobot/workspace/mcp/jira_mcp.py"],
        "env": {
          "JIRA_BASE_URL": "<JIRA_BASE_URL>",
          "JIRA_BEARER_TOKEN": "your_pat_here"
        }
      }
    }
  }
}
```

## 5) 빠른 확인

```bash
nanobot agent --logs -m "MCP 서버 연결 상태를 확인하고 mcp_atlassian_health, mcp_dsqa_health, mcp_jira_health를 호출해줘."
```

로그에 아래와 같은 연결 메시지가 보이면 성공입니다.

- `MCP server 'atlassian': connected`
- `MCP server 'dsqa': connected`
- `MCP server 'jira': connected`

---

## 참고: YouTube Summary MCP

- 서버 파일: `workspace/mcp/youtube_summary_mcp.py`
- 실행 스크립트: `workspace/mcp/run-youtube-mcp.sh`
