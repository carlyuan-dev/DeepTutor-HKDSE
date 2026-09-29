# 开发与验证

## 源码启动

按 [README](../README.md) 安装当前源码及前端依赖后，运行 `python -m deeptutor_cli start`。Python 包名和 CLI 名称仍为 `deeptutor`，以兼容内部导入。

如只检查后端入口：

```sh
python -m deeptutor_cli serve --help
python -m deeptutor_cli serve --host 127.0.0.1 --port 8001
```

完整前端启动优先使用 `start`，它负责前后端地址衔接。开发服务默认认证配置不适合直接对公网开放。

## 配置与资料

运行设置由 `deeptutor/services/config/runtime_settings.py` 和各模型设置服务管理，默认位于运行数据目录下的 `user/settings/`；根 `.env` 文件不是自动加载入口。通过应用设置配置模型供应商、模型名、端点和凭据，不要提交真实设置文件。

当前项目实验使用 DeepSeek 兼容端点 `https://api.deepseek.com` 与 `deepseek-flash`；实验约定的进程环境变量 `OPENAI_API_KEY` 保存的是该供应商凭据，不能仅根据变量名将它发送到 OpenAI。应用设置应明确指定相匹配的供应商端点。模型可用性以你的账户为准。

Embedding 配置独立于聊天模型。历史检索评测使用 `text-embedding-v4`，不要求演示者复用私人向量缓存。导入资料须有相应使用权限；当前仓库不包含完整试卷库或学生记录。

## 核心离线验证

在仓库根运行，模型请求由测试替身隔离：

```sh
python -m pytest -q tests/services/learning/test_learning_chain.py tests/agents/chat/test_learning_chain_flow.py tests/api/test_learning_chain_market.py tests/api/test_learning_loop_reading.py tests/core/test_labeled_step_tool_fallback.py tests/core/test_labeled_step_think_prelude.py tests/services/rag/test_bm25_tokenization.py
node --test web/tests/oral-practice-races.test.mjs web/tests/learning-loop-context.test.mjs
node --test web/tests/paper-stream.test.mjs
python -m pytest -q tests/api/test_market_retrieval.py
```

前端静态检查：

```sh
cd web
./node_modules/.bin/tsc --noEmit --incremental false
```

这些测试验证核心逻辑，不覆盖真实浏览器、麦克风或外部模型的端到端行为。大型检索评测需要另行准备语料和模型服务。

## 修改约定

- Agent 决策与服务端业务校验分层；评分不接受客户端答案键。
- 口语异步回调须保留取消、请求身份、阶段及必要的输入版本校验。
- Learning Loop 的反馈只归属发起它的练习 id；再练保留学科与知识库。
- 修改 BM25 预处理时同步考虑索引与查询侧、缓存失效及小语料边界。
- 不提交 data、.env、数据库、密钥、构建产物或未经确认可再分发的材料。

模块职责和主要调用路径见 [系统架构](ARCHITECTURE.md)。
