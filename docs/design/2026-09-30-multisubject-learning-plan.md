# 三科学习工具链 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有聊天工具循环内交付中、英、数客观题学习链，保持原数学能力兼容。

**Architecture:** 共享学习服务与确定性评分；以显式学科隔离学习会话和成绩。保留数学兼容包装，模型使用通用工具。

**Tech Stack:** Python、SQLite、现有 Agent 工具循环、React/TypeScript。

**Spec:** [已批准的设计](2026-09-30-multisubject-learning.md)。由主窗口直接实施，完成阶段验收后汇报，不自动发布。

**执行状态（2026-09-30）：** 四项功能与验收已完成，结果见 [验收记录](2026-09-30-multisubject-learning-validation.md)。下方保留原计划；任务二、三的后端实现因共享文件合并提交，前端展示和文档分别提交，未推送远端。

## Global Constraints

- 仅四选一客观题；作文、开放题、口语不纳入此次评分链。
- 学科值为 Mathematics、Chinese、English；未知学科拒绝，不静默归为数学。
- 新工具要求明确学科；旧数学调用兼容。凭据、原开发数据和旧公开历史不变。
- 真实模型使用 deepseek-flash；仅核心模拟测试与三科真实链路验收，不扩大评测。

## Review Focus

1. 同聊天切科或恢复旧待答任务时，不串学科状态（任务一、三）。
2. 迁移中断或再次初始化，不丢旧成绩、不重复累计（任务一）。
3. 不同未知中文知识点不碰撞（任务一）。
4. 阅读原文不丢失，答案键不提前泄露（任务二、三）。
5. 模型篡改用户、知识库或提交学科，不改变服务端归属（任务二、三）。

## 任务一：分科状态与兼容迁移

**Files:** 修改 `deeptutor/services/learning/service.py`；新增 `deeptutor/services/learning/subjects.py`、`deeptutor/services/learning/migrations.py`；测试 `tests/services/learning/test_multisubject_learning.py`，保留 `test_learning_chain.py`。

**Interfaces:** `normalise_subject(value: str) -> str`；服务的 `get_state`、`create_attempt`、`explain_concept` 增加关键字 `subject: str = "Mathematics"`。`submit_attempt` 不接受客户端学科，以练习记录为准。

- [ ] 添加失败测试：同一用户、同一聊天创建三科待答题，读取各科只返回本学科；提交英文后数学成绩不变。不同中文未知知识点得到不同稳定 ID。
- [ ] 添加旧版数据库迁移测试：旧会话、待答题、成绩 ID 保留，初始化两次结果相同；迁移失败事务回滚。
- [ ] 运行 `pytest tests/services/learning/test_multisubject_learning.py -q`，确认因缺失分科行为失败。
- [ ] 实现事务迁移：会话唯一键加入 subject，成绩主键加入 subject，旧成绩补 Mathematics；外键引用和旧 ID 不变。主题标识使用学科范围与稳定摘要，保留已有数学已知 ID。
- [ ] 所有状态、薄弱项、待答题查询按 subject 过滤；并发创建继续使用事务与每学习会话唯一待答索引。
- [ ] 运行新测试及原 `tests/services/learning/test_learning_chain.py`，验证重复提交同答案不重复计分、不同答案拒绝、跨用户拒绝。
- [ ] 中文提交：`功能：学习记录支持三科隔离并兼容旧数学数据`。

## 任务二：三科生成与通用工具接入

**Files:** 修改 `deeptutor/services/learning/service.py`、`deeptutor/tools/builtin/__init__.py`、`deeptutor/agents/_shared/tool_composition.py`、`deeptutor/agents/chat/agentic_pipeline.py`；新增通用工具的 `deeptutor/tools/prompting/hints/{en,zh}/*.yaml`，更新 get_learning_state 提示；测试 `tests/agents/chat/test_learning_chain_flow.py`、`tests/agents/chat/test_agentic_parallel_tools.py`。

**Interfaces:** 通用工具 `get_learning_state(subject)`、`explain_learning_concept(subject, ...)`、`create_learning_practice(subject, ...)`、`submit_learning_answer(attempt_id, answers)`。数学旧工具委托同一服务并固定 Mathematics，不重复出现在模型工具集合中。

- [ ] 添加失败测试：工具 schema 枚举三科并要求 subject；新工具被挂载，数学别名仍能由兼容调用执行；非法学科拒绝，伪造用户或未挂载 KB 不生效。
- [ ] 运行上述 Agent 测试确认失败，再接入通用工具、参数注入、提交后的上下文处理和顺序执行约束，避免仅改注册表。
- [ ] 分科生成器沿用统一题目 schema；新增可选题目字段 `passage: str`，阅读题必须非空。服务端保存原文，公开题目返回原文但不返回答案或解析。
- [ ] 分科默认主题、检索查询及讲解提示正确选择；中文用繁体中文材料，英文用英文材料，讲解语言沿用会话设置。生成校验失败不落库。
- [ ] 运行 `pytest tests/services/learning tests/agents/chat/test_learning_chain_flow.py tests/agents/chat/test_agentic_parallel_tools.py tests/api/test_learning_chain_market.py -q`；覆盖建议生成失败仍保留成绩、检索降级状态及旧数学入口。
- [ ] 中文提交：`功能：接入三科讲解与客观题学习工具`。

## 任务三：阅读作答与恢复

**Files:** 修改 `deeptutor/agents/chat/agentic_pipeline.py` 中学习题目转交互等待的构造逻辑；必要时修改 `web/lib/ask-user-state.ts` 及其现有消费者；测试 `tests/agents/chat/test_learning_chain_flow.py`。优先复用现有题干展示，不新增平行答题组件。

**Interfaces:** 阅读原文随保存的 public question 返回，在构造 ask_user 题干时附上；`attempt_id` 与题目 ID 始终指向服务端保存记录。

- [ ] 添加失败测试：带原文的中文、英文题在初次等待及续答载荷中均显示同一原文，公开载荷无答案键；切科后提交旧题仍更新原学科。
- [ ] 使用现有展示字段承载原文；若字段长度限制不足，显式扩展并补一项对应前端行为测试，不截断后声称完整支持。
- [ ] 运行核心链路测试、`node --test web/tests/learning-loop-context.test.mjs`，在已安装依赖环境运行 `npx tsc --noEmit --incremental false`。
- [ ] 中文提交：`功能：阅读练习保留原文并支持分科续答`。

## 任务四：真实验收与使用文档

**Files:** 更新 `README.md`、`docs/QUICKSTART.md`、`docs/EVIDENCE.md`。运行轨迹只保留脱敏必要字段，不公开凭据或私人材料。

- [ ] 在隔离运行目录备份学习数据库，通过新服务初始化迁移；不操作原开发目录用户库。
- [ ] 浏览器分别发送数学判别式、中文短篇阅读、英文语法或短篇阅读请求，真实生成、作答、评分后再次读取状态；保留工具顺序、学科、attempt_id、结果摘要。
- [ ] 在同一聊天切科后返回，验证状态隔离；确认旧数学入口仍可用。人工检查三科样题及答案，区分功能验收与评分质量评估。
- [ ] 运行上述核心回归、前端项目测试和类型检查；记录失败，不把模拟测试写成真实模型质量提升。
- [ ] 文档区分通用聊天与三科学习工具链，给出三科示例请求、客观题范围和恢复边界；删除仅数学适用的过时说明，不修改历史评测结论。
- [ ] 中文提交：`文档：补充三科学习工具链体验与验收说明`。向用户汇报代码、验证结果和未覆盖边界，等待发布决定。
