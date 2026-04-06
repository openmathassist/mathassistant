---
id: openclaw-agent-integration
type: technical-design
created: 2026-04-06
author: hoxide-coder
---

# MathAssistant → OpenClaw Agent 集成方案

## 目标

把 mathassistant 从**直接调用 LLM API** (Claude/OpenAI/Gemini) 改为**调用 OpenClaw multi-agent 系统**。

## 当前架构问题

```
Discord Message
    ↓
OpenClaw Agent (coder/helper/main)
    ↓ (MCP tool call)
MathAssistant MCP Server
    ↓ (内部直接调 API)
Claude/OpenAI/Gemini API
```

**问题**：
1. 每个 MCP tool 内部自己做 LLM 调用，无法利用 OpenClaw 的 agent 路由
2. 无法使用 workspace memory、skills、sub-agent orchestration
3. 重复造轮子（OpenClaw 已经有完整的 agent 系统）

## 目标架构

```
Discord Message
    ↓
OpenClaw Agent (math-research orchestrator)
    ↓ (MCP tool call)
MathAssistant MCP Server (thin wrapper)
    ↓ (sessions_spawn)
OpenClaw Sub-agents:
    - coder: 复杂数学推导、代码生成
    - helper: 文献查找、简单问答
    - main: 用户交互、决策
    ↓ (results)
MathAssistant 整理结果 → Git commit
```

## 改造计划

### Phase 1: 添加 OpenClaw Agent 调用接口

新增 `mathassistant/openclaw/` 模块：

```python
# openclaw/client.py
import subprocess
import json
from pathlib import Path

class OpenClawClient:
    """Call OpenClaw agents via CLI."""
    
    def call_agent(self, agent_id: str, message: str, timeout: int = 300) -> str:
        """Spawn an OpenClaw agent and get result."""
        result = subprocess.run(
            ["openclaw", "agent", "call", agent_id, "--message", message],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout
    
    def spawn_session(self, agent_id: str, task: str) -> str:
        """Spawn a persistent session, return session key."""
        result = subprocess.run(
            ["openclaw", "sessions", "spawn", 
             "--agent-id", agent_id,
             "--mode", "session",
             "--task", task],
            capture_output=True,
            text=True
        )
        # Parse session key from output
        return result.stdout.strip()
```

### Phase 2: 改造 LLM 调用点

改造 `detect()`, `create_draft()`, `summarize()` 等函数：

**Before**:
```python
async def detect(project_dir, content, context):
    llm = get_llm_backend()  # 直接调 Claude API
    response = await llm.complete(prompt, content)
    return parse_response(response)
```

**After**:
```python
async def detect(project_dir, content, context):
    client = OpenClawClient()
    # 调用 coder agent 做复杂分析
    task = f"""Analyze this math discussion for problem signals:
    
Content: {content}
Context: {context}

Look for:
- Conjectures
- Theorem proposals  
- Proof requests

Respond with JSON: {{"detected": bool, "candidates": [...]}}"""
    
    result = client.call_agent("coder", task)
    return parse_response(result)
```

### Phase 3: 多 Agent 协作

复杂任务使用多个 agents：

```python
async def draft_problem(project_dir, source_text, context, problem_type):
    client = OpenClawClient()
    
    # Step 1: coder 起草问题框架
    draft_task = f"Draft a {problem_type} from: {source_text}"
    draft = client.call_agent("coder", draft_task)
    
    # Step 2: helper 查找相关文献
    lit_task = f"Find references for: {source_text[:200]}"
    refs = client.call_agent("helper", lit_task)
    
    # Step 3: main 整理成最终格式
    finalize_task = f"Format this problem:\n{draft}\n\nReferences:\n{refs}"
    result = client.call_agent("main", finalize_task)
    
    return parse_problem_draft(result)
```

### Phase 4: 移除直接 LLM 依赖

修改 `config.py`：
- 保留 `llm_backend` 作为 fallback（可选）
- 默认使用 `openclaw` backend
- 新增 `openclaw_agent_mapping` 配置

```python
@dataclass
class Config:
    backend: str = "openclaw"  # "openclaw" | "claude" | "openai" | ...
    # OpenClaw 配置
    openclaw_default_agent: str = "coder"
    openclaw_helper_agent: str = "helper"
    openclaw_main_agent: str = "main"
    # Fallback LLM 配置（可选）
    llm_backend: str | None = None
    llm_api_key: str | None = None
```

### Phase 5: 集成 designspec 功能

根据 designspec 要求，添加：

1. **Intent 分析** (`analyze_intent`)
   - 调用 helper agent 做轻量级分类
   
2. **Prove Agent 集成** (`start_prove_attempt`)
   - 调用 coder agent 长时间运行
   - 使用 `sessions_spawn` 保持会话

3. **文献检索** (`search_literature`)
   - 调用 helper agent + web search skill

## 关键决策

### Q1: 每个 tool call 都 spawn 新 agent，还是复用 session？

**Option A: 每次 spawn（简单，无状态）**
- Pros: 简单，无并发问题
- Cons: 慢，每次都要初始化

**Option B: 复用 session（性能好）**
- Pros: 快，有上下文记忆
- Cons: 需要管理 session lifecycle

**建议**: Phase 1 用 A，Phase 2 考虑 B

### Q2: 如何传递 workspace context？

**方案**: 通过 `--cwd` 或环境变量传递项目路径

```python
subprocess.run(
    ["openclaw", "agent", "call", "coder", "--message", task],
    cwd=project_dir,  # 设置工作目录
    env={"MATHASSIST_PROJECT": str(project_dir)}
)
```

### Q3: 错误处理？

- Agent 超时 → fallback 到 direct LLM（如果配置了）
- Agent 返回格式错误 → retry with clarification prompt
- 所有错误记录到 log.md

## 实施顺序

1. ✅ 修复 asyncio.run() 冲突（已完成）
2. **实现 OpenClawClient 基础类**
3. **改造 detect_problems 作为试点**
4. **逐步改造其他 tools**
5. **添加 designspec 中的高级功能**
6. **测试 multi-agent 协作**

## 与现有工作流的关系

- **nilpotent-orbit-induction 项目**: 继续用文件方式管理
- **mathassistant MCP**: 变成 OpenClaw 的 coordinator
- **designspec**: 指导 agent 工作流设计
