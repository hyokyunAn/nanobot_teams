# Atlassian Confluence MCP (PAT)

이 폴더에는 Confluence PAT 기반 MCP 서버가 있습니다.

- 서버 파일: `workspace/mcp/atlassian_confluence_mcp.py`
- 실행 스크립트: `workspace/mcp/run-atlassian-mcp.sh`

## 1) 환경변수 준비

Confluence PAT 인증은 `Authorization: Bearer <PAT>` 방식으로 동작합니다.

```bash
export CONFLUENCE_BASE_URL="https://your-domain.atlassian.net/wiki"
export CONFLUENCE_PAT="your_pat_here"
```

선택 옵션:

```bash
export CONFLUENCE_TIMEOUT_SECONDS="30"
export CONFLUENCE_VERIFY_SSL="true"
```

## 2) 로컬 실행

```bash
./workspace/mcp/run-atlassian-mcp.sh
```

또는:

```bash
python workspace/mcp/atlassian_confluence_mcp.py
```

`stdio` MCP 서버라서 실행 후 대기 상태가 정상입니다.

## 3) nanobot 연결 (`~/.nanobot/config.json`)

아래 `tools.mcpServers` 항목을 추가/병합하세요.

```json
{
  "tools": {
    "mcpServers": {
      "atlassian": {
        "command": "python",
        "args": ["/Users/ahk/github_codes/nanobot/workspace/mcp/atlassian_confluence_mcp.py"],
        "env": {
          "CONFLUENCE_BASE_URL": "https://your-domain.atlassian.net/wiki",
          "CONFLUENCE_PAT": "your_pat_here"
        }
      }
    }
  }
}
```

nanobot 실행 후, MCP 툴은 `mcp_<server>_<tool>` 이름으로 노출됩니다.

- `mcp_atlassian_health`
- `mcp_atlassian_list_spaces`
- `mcp_atlassian_search_pages`
- `mcp_atlassian_get_page`
- `mcp_atlassian_create_page`
- `mcp_atlassian_update_page`

## 4) 빠른 확인

```bash
nanobot agent --logs -m "MCP health 체크해줘"
```

로그에 `MCP server 'atlassian': connected`가 보이면 연결 성공입니다.

---

# YouTube Summary MCP

유튜브 영상 자막을 읽어 요약하는 MCP 서버입니다.

- 서버 파일: `workspace/mcp/youtube_summary_mcp.py`
- 실행 스크립트: `workspace/mcp/run-youtube-mcp.sh`

## 1) 로컬 실행

```bash
./workspace/mcp/run-youtube-mcp.sh
```

옵션 환경변수:

```bash
export YOUTUBE_MCP_TIMEOUT_SECONDS="25"
export YOUTUBE_MCP_USER_AGENT="Mozilla/5.0 ..."
```

## 2) nanobot 연결 (`~/.nanobot/config.json`)

```json
{
  "tools": {
    "mcpServers": {
      "youtube": {
        "command": "python",
        "args": ["/Users/ahk/github_codes/nanobot/workspace/mcp/youtube_summary_mcp.py"]
      }
    }
  }
}
```

노출되는 tool 이름:

- `mcp_youtube_health`
- `mcp_youtube_fetch_transcript`
- `mcp_youtube_summarize_video`
