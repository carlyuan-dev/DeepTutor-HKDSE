# 系统架构

## 交互方式与状态边界

数学学习 Agent 是模型驱动的工具循环；Market 的 Learning Loop 是用户操作驱动的跨页面反馈链路。二者复用模型、检索和学习能力，但使用不同的状态管理与持久化机制。

```text
聊天请求 → ChatOrchestrator → chat 工具循环 → 学习工具 → SQLite 学习记录
                                   ↕
                             ask_user 暂停与续答

Market 页面 → FastAPI 功能接口 → 生成／批改／检索服务
     ↕
浏览器练习上下文 → 本次反馈 → 原学科再练／闪卡
```

## 目录职责

工作台的通用、中、英文试卷生成请求由 `web/lib/market-api.ts` 分别构造，共用私有 `readPaperResponse` 读取 progress/done/error NDJSON 响应。口语流的事件类型与取消生命周期不同，使用独立处理逻辑。

| 目录 | 职责 |
| --- | --- |
| `deeptutor/runtime/` | 通用编排入口、注册、启动；主要沿用框架 |
| `deeptutor/core/agentic/` | 模型步进、动作协议与工具执行 |
| `deeptutor/agents/chat/` | 上下文与工具组合、等待用户回复 |
| `deeptutor/services/learning/` | 数学题目、私有答案、作答和成绩的服务端状态 |
| `deeptutor/api/routers/` | Market、各学科及 WebSocket 接口 |
| `deeptutor/services/rag/` | 文档摄入、索引、检索与缓存 |
| `web/app/(utility)/market/` | 工作台功能页面与交互控制 |
| `web/lib/learning-loop-context.ts` | 浏览器练习封装和结果归属 |
| `tests/`、`web/tests/` | 后端单测和前端逻辑／竞态验证 |

### 英文工作台模块

英文工作台的接口按能力分为 `api/routers/hkdse_english/paper.py`（阅读试卷）、`essay.py`（作文评分）、`integrated.py`（综合技能）和 `oral.py`（口语）。包的 `__init__.py` 仅汇总路由，应用统一挂载到 `/api/v1/hkdse/english`。修改某项能力时，从对应模块入手；请求模型和提示词与其接口放在一起。

## 数学学习 Agent

阅读顺序：

1. `deeptutor/runtime/orchestrator.py`：进入既有能力与工具体系。
2. `deeptutor/agents/chat/agentic_pipeline.py`：工具参数上下文注入与暂停作答。
3. `deeptutor/tools/builtin/__init__.py`：学习状态、出题、评分、讲解工具包装。
4. `deeptutor/services/learning/service.py`：题目、答案键、用户归属及评分事务。
5. `deeptutor/services/session/turn_runtime.py`、`deeptutor/api/routers/unified_ws.py`：执行任务、事件回放与回复队列。

模型看到工具返回结果后可以选择下一工具；选择受用户请求和工具提示约束，不代表自主教学策略已验证。出题后保存待答题目，客户端不获取私有答案键。提交按服务端题目和当前用户核验，事务中更新作答、成绩与学习记录。

同一 attempt 已完成时重复提交返回已有成绩，不再次累加；即使第二次答案不同，也不是“修改成绩”。同进程断线可重新订阅仍在运行的任务与待答事件；进程内回复队列不是可跨进程恢复的完整 Agent 栈。

`deeptutor/core/agentic/labeled_step.py` 修复有原生工具调用但缺少文本动作标签时的识别问题；`loop.py` 与工具服务仍负责动作冲突和业务参数检查，不意味着所有工具具备严格 JSON Schema 校验。

## 英语口语模拟

主入口：`web/app/(utility)/market/hkdse/english/oral-practice/page.tsx`；请求传输：`web/lib/market-api.ts`；生成接口：`deeptutor/api/routers/hkdse_english/oral.py`。

前端维护讨论议程、下一角色和阶段计时；后端按传入角色与议题生成发言，也保留兼容的历史推导分支。阶段切换先取消请求、清理排队和预取，再进入下一阶段。

回调写入前检查取消状态、请求序号与当前阶段。部分语音转写触发的预取额外绑定输入版本与规范化文本；最终转写改变时作废旧预取，一致时才允许复用。规范化只保守处理空白，不把否定变化或同义改写视为同一输入。

这些机制保护字幕与播报输入，不证明模型供应商立即停止生成或计费，也不是刷新后会话恢复。

## 知识库与检索

工作台的通用试卷、闪卡、学习工具和中英文试卷通过 `deeptutor/services/retrieval_context.py` 复用上下文读取与普通异常回退。路由仍负责构造查询和过滤参数：中文按文言／白话，英文按体裁；约束回退时保留原告警与可用文本。服务延迟导入，取消信号继续向上传播。数学学习服务需要额外的状态和来源信息，不使用这个纯文本适配器。

阅读 `deeptutor/services/rag/pipelines/llamaindex/` 下的 `document_loader.py` → `pipeline.py` → `retrievers.py` → `bm25_tokenization.py` → `storage.py`，以及 `deeptutor/services/rag/metadata_constraints.py`。

摄入负责文档加载、切块和索引；查询经过元数据过滤与 Dense／BM25 候选检索，可通过 RRF 融合。中文处理使用重叠字符二元组，统一两侧预处理；缓存校验包含分词配置，避免修复后继续复用旧索引。小规模语料候选深度受实际节点数量约束。

评测中的方案对比不代表所有调用入口采用同一默认策略。具体参数与数据使用范围见 [测试与检索评测](EVIDENCE.md)。

## Learning Loop

先读 `web/lib/learning-loop-context.ts` 与 `web/types/market.ts`，再读 Market 下的 `paper-forge`、中英文 `paper-generator`、`exam-grader` 和 `flash-deck` 页面；后端对应 `paper_forge.py`、`exam_grader.py`、`market_tools.py` 及学科接口。

练习封装关联 id、学科、来源入口、知识库、试卷与答案。批改请求携带阅读原文；反馈以该练习 id 单独保存，再练返回原入口并携带练习标识。薄弱项取本次反馈，不从旧全局键猜测。

保存结果前后检查当前练习归属；结果按 id 写入独立 key，防止覆盖新练习封装。页面还用请求序号拒收旧评分与闪卡生成结果。这是浏览器存储与交互保护，不是 SQLite 事务，也不提供 localStorage 跨标签页 CAS。
