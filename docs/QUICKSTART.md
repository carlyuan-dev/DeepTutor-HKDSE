# 从零体验 HKDSE 功能

本指南使用仓库内的小型原创材料，走真实模型调用和真实知识库检索。不需要作者的数据库、试卷库或向量缓存。

你需要可访问的 LLM 服务；体验知识库时还需要 Embedding 服务。凭据由你提供，调用可能收费。先生成少量题目，避免一开始运行整套试卷。

## 1. 安装并启动

准备 Python 3.11+、Node.js 22+ 和 npm。以下命令适用于 macOS / Linux shell：

```sh
git clone https://github.com/carlyuan-dev/DeepTutor-HKDSE.git
cd DeepTutor-HKDSE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cd web
npm ci
cd ..
python -m deeptutor_cli start
```

Windows PowerShell 的虚拟环境激活命令为 `.venv\Scripts\Activate.ps1`；其余步骤对应执行。平台实测范围见本文末尾，不将这些说明视为全平台验收。

打开启动日志给出的前端地址。默认前端 `http://localhost:3782`，后端 `http://localhost:8001`。首次页面编译可能需要等待。一直在仓库根目录启动，运行数据会在该目录的 `data/` 下创建；不要把 `data/` 提交到 Git。

不要安装 PyPI 原版替代本源码，也不要复制作者的 `.env`：根 `.env` 不会自动加载。暂不需要搜索服务、OCR、PocketBase 或 Manim。

## 2. 配置 LLM

打开 `/settings/llm`，添加配置（Profile）与模型：

1. 选择与你的服务对应的供应商／兼容协议。
2. 填写该服务的 Base URL 和 API Key。
3. 填写账户实际可用的 Model ID，选择其为活动模型。
4. 使用 `Run test` 检查连通性，然后点击设置页的 `Apply` 应用配置。刷新页面确认配置保留。

数学 Agent 需要模型支持工具调用；仅能生成普通文本的服务不足以体验工具链。不同模型输出可能不同，不要求逐字复现示例。

项目此前使用 DeepSeek 兼容服务与 `deepseek-flash`；这不是通用默认值，请确认你的账户支持所填模型。不要把 DeepSeek 的 Key 填到 OpenAI 端点。LLM Key 也不能默认用于另一供应商的 Embedding 服务。

配好 LLM 后即可先做下面 A、B 两条路线，不必等待知识库导入。

## 3. 配置 Embedding 并导入三个小知识库

打开 `/settings/embedding`，添加供应商、API Key 和模型。该页面的 `Endpoint URL` 是完整 Embedding 接口地址（而不是照抄 LLM 的 Base URL）；优先使用所选供应商提供的默认地址。运行连接测试，核对返回维度并应用配置。已有索引后改变模型或维度，需要重新建库。

在 `/knowledge` 创建下列三个知识库，每库只上传对应的一份 TXT，等待状态显示完成后再使用：

| 名称 | 仓库内文件 |
| --- | --- |
| `demo-hkdse-chinese` | `examples/hkdse/chinese/reading.txt` |
| `demo-hkdse-english` | `examples/hkdse/english/reading.txt` |
| `demo-hkdse-maths` | `examples/hkdse/maths/quadratics.txt` |

不要导入整个 examples 目录。已有同名库时先使用已有库；不要为重试删除个人知识库。

也可以在完成模型配置后，从仓库根目录用现有 CLI 导入：

```sh
python -m deeptutor_cli kb create demo-hkdse-chinese --doc examples/hkdse/chinese/reading.txt
python -m deeptutor_cli kb create demo-hkdse-english --doc examples/hkdse/english/reading.txt
python -m deeptutor_cli kb create demo-hkdse-maths --doc examples/hkdse/maths/quadratics.txt
```

CLI 和网页应使用同一运行目录。同名库会被拒绝创建，不覆盖旧库。小型资料足以体验链路，不代表课程知识覆盖率或历史检索指标。

## A. 数学学习 Agent

在 `/chat` 选择普通聊天能力，新建会话并发送：

> 请先读取我的数学学习记录，再给我一道判别式的基础选择题。请用练习工具出题并等待我作答，暂时不要透露答案。

应看到读取学习记录和创建练习的工具过程，随后出现等待作答交互。第一次没有成绩属于正常状态，不需要导入旧记录。完成作答后，让系统提交评分；再询问：

> 请重新读取我的学习记录，告诉我刚才这道练习的得分和下一步建议。

检查返回状态中是否出现本次作答。如果只返回普通题目文字、没有工具调用或作答交互，先检查所选能力、活动模型和工具调用兼容性。

学习记录保存于服务端；等待作答的执行任务只支持同进程续接，重启后不保证恢复原暂停栈。

## B. 英语口语模拟

进入 `/market/hkdse/english/oral-practice`：

1. 选择 Education 等分类，点击 `Start Practice`，会载入内置原创话题。
2. 阅读材料，点击 `Skip Preparation & Start Discussion` 可跳过准备时间。
3. 观察 AI 角色发言及字幕，使用 `Speak` 开始回答，`Stop` 结束本次录音。
4. 点击 `Skip to Part B` 进入个人回答，按页面计时完成后查看反馈。

首次使用允许麦克风权限。语音识别依赖浏览器、设备及其语音服务，页面显示不支持时无法完成语音作答。刷新会重新开始，不恢复上一场口语考试。

## C. Learning Loop：练习、批改、再练、闪卡

进入 `/market/paper-forge`：

- Knowledge Base：`demo-hkdse-maths`。
- Subject：`HKDSE Mathematics`。
- Topic Focus：`一元二次方程：判别式与实根个数`。
- 数量：3；难度：Easy；题型：Multiple Choice。

生成后自行作答并提交，进入批改页。可以有意答错一题观察反馈，但生成题目的答案和模型反馈仍需要自己核对。

在结果页先选择 `Review with FlashDeck`，查看由本次薄弱项生成的闪卡（默认 15 张），点击卡片翻面，再选择熟悉程度。若模型偶发返回不完整内容，服务会额外尝试一次；仍失败则显示重试提示。

用浏览器返回该批改结果，选择 `Retake Exam`，检查原学科、原知识库和本次薄弱项被带回生成页。题量、题型和难度不沿用上一轮，体验时重新选 3 道基础选择题。再练会产生新练习，不要把上一份反馈当成新练习的成绩。

若本次没有薄弱项，不保证出现相同的再练内容。浏览器必须允许本地存储；不要在同一浏览器里同时开多份练习互相替换当前上下文。

英文、中文阅读试卷也有对应入口；先走通这个三题版本，再尝试学科专属页面。额外的英文作文输入在 `examples/hkdse/inputs/english-essay.txt`，可粘贴到 `/market/hkdse/english/essay-coach`，选择 Feature Article 和默认单路批改。

## D. 确认课程检索真的发生

新建聊天，附加对应示例知识库，复制 [示例清单](../examples/hkdse/README.md) 的检索问题。要求系统先检索该库再回答，并展示依据。

分别核对三科工具返回的片段是否包含清单中的依据。看到正确答案本身还不够，模型也可能凭常识回答；必须有检索调用及相关返回内容。若所选页面不展示片段，可在聊天检索工具结果中核对。

部分生成接口检索失败会降级为纯模型生成。`grounded`（若接口提供）只表示取得了检索上下文，不证明每一句生成内容均获支持。本指南不重新比较 Dense/BM25/RRF，也不复现历史 MRR 数字。

## 常见阻塞

| 现象 | 优先检查 |
| --- | --- |
| 页面打开但调用失败 | 后端是否仍运行；设置中的活动模型、端点和凭据是否匹配；是否应用配置 |
| 401／403 | 服务账户、Key、权限；不要通过关闭 TLS 校验解决 |
| 知识库一直失败 | Embedding 连接测试、模型维度、导入进度中的错误；暂不导入扫描件 |
| CLI 创建的库网页看不到 | 是否在同一仓库根目录运行，是否设置了不同的 `DEEPTUTOR_HOME` |
| Agent 不出现作答交互 | 是否使用聊天能力和支持工具调用的模型；查看工具返回的错误 |
| 口语无法作答 | 麦克风权限、浏览器语音识别支持及网络；刷新会丢失本场进度 |
| 再练要求重新开始 | 当前练习被替换或原知识库已不存在；从新练习开始，不手动篡改存储 |

## 验收范围

2026-09-29 在 macOS Apple Silicon、Python 3.11.6、Node.js 24.18.0、npm 11.16.0 上，从公开仓库重新克隆并安装依赖，使用空数据目录进行验收。LLM 使用 `deepseek-flash`，Embedding 使用 `text-embedding-v4`（所用端点实际输出 1024 维，按实际结果配置；不是要求所有服务填相同维度）。未复制旧数据库或索引。Windows / Linux 未实测。

| 项目 | 验证结果 |
| --- | --- |
| 安装、启动、配置 | `pip install -e '.[dev]'`、`npm ci`、`pip check` 通过；空配置能打开页面；通过设置 API 应用模型后，浏览器能选择模型，重启后保留 |
| 数学 Agent | 浏览器中真实调用学习状态、出题、等待用户选择、提交评分；后续请求重新读取到本次 1/1 成绩 |
| Learning Loop | 浏览器中生成三题、作答批改、生成 15 张闪卡并翻面；再练继承学科、知识库、薄弱项并生成新题 |
| RAG | 三科各一份示例文件真实建库，三条直接检索均返回相应原文；英文聊天验证了检索调用及材料依据回答 |
| 口语 | 浏览器加载内置话题，真实生成多角色 Part A 发言并切换到 Part B；麦克风采集、ASR、实际播报效果及语音作答后的反馈仍需人工验收 |

验收也发现并处理了两个问题：Embedding 设置与服务实际输出维度不一致时，需要改正配置并重建该示例索引；闪卡遇到不完整 JSON 时原先直接失败，现有结构校验和一次受限重试。单次链路通过不代表模型结果始终正确。
