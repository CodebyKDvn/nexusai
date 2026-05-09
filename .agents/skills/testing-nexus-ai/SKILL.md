# Testing Nexus AI

## Overview
Nexus AI is a multi-agent AI development platform with a FastAPI web server, WebSocket chat, and CLI interface. Testing covers API endpoints, web UI, and agent routing.

## Devin Secrets Needed
- `NVIDIA_API_KEY` (optional) — enables LLM-powered agent responses. Without it, the system runs in "rule-based mode" where agents return stub responses. All orchestration logic (crew assembly, task routing, keyword matching) works without an API key.

## Environment Setup
```bash
cd /home/ubuntu/repos/nexus-ai
pip install -e ".[dev]"
```

## Starting the Web Server
```bash
nexus serve --port 8000
```
- Server runs on `http://localhost:8000`
- Shows "Rule-based mode (no API key)" if `NVIDIA_API_KEY` is not set
- The server must be started in background mode for browser testing

## Key API Endpoints

### GET /api/status
Returns server health, agent count (11), provider, model, and API key status.

### GET /api/crew?task=...
Dynamic Crew Assembly endpoint. Classifies a task description and returns the optimal agent team.
- Returns: `{category, agents, parallel, confidence, reasoning}`
- Categories: `full_stack`, `frontend`, `backend`, `bug_fix`, `design`, `research`, `testing`, `code_review`, `planning`, `general`
- Full-stack detection: when BOTH frontend AND backend keywords are present, returns `full_stack` with `parallel: true`
- Missing `task` param returns `{"error": "Provide a 'task' query parameter"}`

### GET /api/task-graph
Returns task graph state summary: `{total, by_status, all_completed, iteration}`
- On fresh server: `{total: 0, by_status: {}, all_completed: true, iteration: 0}`

### WebSocket /ws
Real-time chat endpoint. Messages are sent as JSON with `message` field.

## Testing Patterns

### API Testing via Browser
Navigate directly to API endpoint URLs in Chrome. Use "Pretty-print" checkbox for formatted JSON.

### Web Chat UI Testing
1. Navigate to `http://localhost:8000`
2. Sidebar shows 11 agents with green "Connected" status
3. Type message in input and click send button (Enter key may not work in computer use tool — use click on send button instead)
4. Messages route: user → orchestrator → specialist agent → (optional critic review) → user
5. Activity log in sidebar shows routing chain

### Agent Routing Verification
- "React", "CSS", "component", "UI" → `frontend_developer`
- "API", "database", "server", "endpoint" → `backend_developer`
- "bug", "fix", "crash", "error" → `debugger`
- "test", "testing" → `qa`
- "ui design", "ux design", "mockup" → `ux_ui_designer`
- Combined frontend + backend keywords → `full_stack` crew with `parallel: true`

### Suggestion Cards
The main page has 4 suggestion cards: "Build a REST API", "Design chat architecture", "Debug auth flow", "Write test suite". Clicking them sends the text as a chat message.

## Known Behaviors
- In rule-based mode, agents return structured stub responses (not real code)
- The critic agent automatically reviews developer output before returning to user
- The send button in the chat input may appear disabled until text is typed
- Chrome's `key: Return` action may fail with computer use tool — prefer clicking the send button directly

## Running Unit Tests
```bash
pytest tests/ -v
pytest tests/test_orchestration.py -v  # orchestration-specific tests
```

## Code Quality
```bash
ruff check src/ tests/
mypy src/
```
