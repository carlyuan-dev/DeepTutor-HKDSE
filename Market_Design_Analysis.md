# Market Tab × Proposal 差距分析与全面学习工具设计

> 文档目的：对照 `CS_Project_Proposal.docx`（On-Premise AI Examination & Knowledge Management System），分析 Market tab 已实现 / 未实现的功能，列出补齐 proposal 所需的工作，并给出一套全面的、多样化的学习工具设计方案。
>
> 生成日期：2026-06-23

---

## 一、Proposal 的核心要求（基线）

| # | 要求 | 关键词 |
|---|------|--------|
| R1 | **自动出题** — 用 RAG 索引校本教材 + 历年试卷，生成对齐 HKDSE 课纲的考试材料 | RAG / 校本 / 课纲对齐 |
| R2 | **自动批改与反馈** — 本地 LLM 对照**官方评分标准**评估学生作答，即时给分 + 个性化建设性反馈；采用 **CoT** 策略，把学生答卷与 **RAG 检索到的 rubric** 比对来论证给分 | 官方 rubric / CoT / 个性化反馈 |
| R3 | **全离线 / Apple Silicon (MLX) / PDPO 合规** — 100% 数据驻留本地 | 本地 MLX / 离线 / 隐私 |
| R4 | **架构** — LangChain 检索管线；FastAPI 后端经 PyInstaller 编成受保护二进制；React + Tauri 原生 macOS 桌面应用 (.dmg) | Tauri / PyInstaller |
| R5 | **交付物** — 课纲向量库、量化 MLX 权重、出题+批改模块、**自动化反馈报告** | 向量库 / 反馈报告 |

---

## 二、Market tab 现状盘点（已实现）

Market 页面 (`web/app/(utility)/market/page.tsx`) 分两区：**Learning Loop**（通用三件套）+ **HKDSE 学科**（中/英/数）。

后端路由全部真实存在（`deeptutor/api/routers/`），**没有 stub**，但实现模式统一为「LLM 薄封装 + 可选浅层 RAG」。

### 2.1 Learning Loop（通用闭环）

| 工具 | 路由 | 后端 endpoint | 实现 | 接地（RAG）| 备注 |
|------|------|--------------|------|-----------|------|
| **PaperForge** 出题 | `/market/paper-forge` | `POST /api/v1/paper-forge/generate`（流式）| ✅ | ⚠️ 可选、单次查询、截断 6000 字 | RAG 失败时静默降级为纯 LLM |
| **ExamGrader** 批改 | `/market/exam-grader` | `POST /api/v1/exam-grader/grade` | ✅ | ❌ 无 | 对照 LLM 自己生成的答案批改，非官方标准 |
| **FlashDeck** 间隔重复 | `/market/flash-deck` | `POST /api/v1/flash-deck/generate` | ✅ | ❌ 无 | SM-2 算法在前端，自动吸收 ExamGrader 的弱项 |

### 2.2 HKDSE 学科

| 学科 | 子工具 | 后端 endpoint | 实现 | 接地 |
|------|--------|--------------|------|------|
| **中文** | 试卷生成 | `POST /hkdse/chinese/generate-paper`（流式）| ✅ | ⚠️ 浅层 RAG，截断 3000 字 |
| | 作文批改 | `POST /hkdse/chinese/essay-grade` | ✅ | ❌ 通用 rubric（内容/表达/组织），非官方 |
| | 文言文精读 | `POST /hkdse/chinese/analyze-classical` | ✅ | ❌ 纯 LLM |
| **英文** | 试卷生成 | `POST /hkdse/english/generate-paper`（流式）| ✅ | ⚠️ 浅层 RAG |
| | 作文教练 | `POST /hkdse/english/essay-grade` | ✅ | ❌ 通用 rubric |
| | 综合能力 (Paper 3) | `POST /hkdse/english/integrated-skills` | ✅ | ❌ 纯 LLM |
| **数学** | 试卷生成 | （复用 PaperForge）| ✅ | ⚠️ |
| | 解题步骤批改 | `POST /hkdse/maths/step-check` | ✅ | ❌ 纯 LLM |
| | 专题练习 | `POST /hkdse/maths/topic-drill` | ✅ | ❌ 纯 LLM |

**结论：功能广度不错（9 个 endpoint），但深度浅** —— 几乎都是「prompt → LLM → JSON」，未真正用上 proposal 的两大支柱（深度 RAG 接地、官方评分标准比对）。

---

## 三、差距分析（对照 Proposal）

| 差距 | Proposal 要求 | 现状 | 严重度 |
|------|--------------|------|--------|
| **G1 本地离线 LLM** | 本地 MLX，100% 离线，PDPO 合规 | `.env` 配的是**云端 DeepSeek**（`api.deepseek.com`）。基础设施支持本地（`local_provider.py` 支持 LM Studio/Ollama/vLLM），但当前未启用 | 🔴 高（违背项目根本卖点）|
| **G2 RAG 深度接地** | 题目「grounded in verified school documents」 | 单次 `search()`、内容截断、失败静默降级为纯 LLM（有幻觉风险）| 🔴 高 |
| **G3 官方评分标准批改** | 「compares student scripts with **RAG-retrieved rubrics**」+ CoT 论证给分 | ExamGrader 对照 LLM 自生成答案；作文用通用 rubric，**没有检索官方 marking scheme** | 🔴 高 |
| **G4 课纲向量库 / 历年试卷入库** | Curriculum Vector Store（校本教材 + 历年卷 + 评分标准）| `HKDSE_Paper/` 下有 2012 真题 PDF，但**无入库管线**，工具默认无 KB | 🟠 中高 |
| **G5 CoT 批改策略** | 显式 Chain-of-Thought 论证给分 | 单轮 JSON 输出，无显式推理链 | 🟠 中 |
| **G6 自动化反馈报告** | 交付物 #8「Automated Feedback Reports」 | 有逐题反馈，但**无聚合的学生表现报告 / 导出 / 历时追踪** | 🟠 中 |
| **G7 Tauri 桌面 + .dmg** | React + Tauri 原生 macOS，.dmg 安装包 | 现为 Next.js Web 应用 | 🟡 中（超出 Market 范围，但属交付物）|
| **G8 PyInstaller 受保护二进制** | 编译后部署到校内网 | 未见打包配置 | 🟡 低（部署阶段）|

---

## 四、补齐 Proposal 所需工作（按优先级）

### P0 — 必须做（决定项目是否「成立」）

1. **切换到本地 LLM（G1）**
   - 用 **LM Studio**（原生支持 Apple Silicon MLX 后端）或 `mlx_lm.server` 起 OpenAI 兼容端点。
   - `.env` 改为 `LLM_BINDING=lm_studio`（或 openai-compatible），`LLM_HOST=http://localhost:1234/v1`。
   - 在 UI 加「离线模式」徽章 + 启动自检（探测本地端点可达），明确告知「数据不出本机」。

2. **建课纲向量库 + 历年试卷入库管线（G4）**
   - 新增 ingestion 脚本：把 `HKDSE_Paper/`（题卷 + 答卷/marking scheme）+ 校本教材 PDF 解析 → 切块 → 嵌入 → 写入按「学科/卷次/年份/题型」打标签的 KB。
   - **关键：marking scheme 单独入库**，作为批改时的检索源（支撑 G3）。

3. **批改对照官方评分标准 + CoT（G3、G5）**
   - 批改前先 `RAG 检索该题/该体裁的官方 marking scheme`；
   - prompt 改为显式 CoT：先逐点比对学生答卷与 rubric 要点 → 再给分 → 再生成反馈；
   - 输出结构里保留「评分依据（哪些 rubric 点命中/缺失）」。

### P1 — 强烈建议（让现有工具达到 proposal 质量）

4. **深化 RAG 接地（G2）**：多查询（题型/知识点各检索）、Top-K 合并、来源引用回填到题目；去掉「静默降级」，改为显式提示「当前未接知识库，题目可能偏离课本」。
5. **自动化反馈报告（G6）**：把每次批改结果落库 → 生成「学生表现报告」（强弱项雷达、历时趋势、错题归类、下一步建议），支持导出 PDF。

### P2 — 交付物收尾（部署阶段）

6. Tauri 封装 + .dmg（G7）；7. FastAPI → PyInstaller 受保护二进制（G8）。

---

## 五、全面学习工具设计（丰富 Market 的多样化能力）

设计原则：**每个工具都建立在「RAG 接地 + 官方标准」之上**，而非孤立的 LLM 调用；并围绕「**学 → 练 → 测 → 评 → 复习**」的学习闭环组织。下面按能力簇分类，标注是否为**新增**及优先级。

### 簇 A — 出题与组卷（Generation）

| 工具 | 说明 | 状态 |
|------|------|------|
| 通用出题 PaperForge | 已有 | ✅ 深化 RAG |
| **整卷模拟（Full Mock Paper）** | 按真实 HKDSE 卷次结构（分卷、题量、配分、时限）生成整套模拟卷 | 🆕 P1 |
| **按真题改编（Past-Paper Variant）** | 检索历年真题 → 同知识点同难度改编出新题（防背题）| 🆕 P1 |
| **难度自适应出题** | 依学生历史表现动态调节难度（IRT/简单难度梯度）| 🆕 P2 |
| **题目银行管理（Question Bank）** | 教师侧：收藏、标签、复用、组卷 | 🆕 P2（教师向）|

### 簇 B — 批改与反馈（Marking & Feedback）—— Proposal 核心

| 工具 | 说明 | 状态 |
|------|------|------|
| 客观题/简答批改 ExamGrader | 已有 | ✅ 改为对照官方标准 |
| 中/英作文批改 | 已有 | ✅ 接入官方 rubric + CoT |
| 数学解题步骤批改 | 已有 | ✅ 增加 rubric/给分点 |
| **结构化长题批改（Structured Q）** | 理科/通识多步骤大题，按 marking scheme 逐点给分 | 🆕 P1 |
| **口语评估（Speaking, Paper 4）** | 本地 ASR（如 whisper.cpp）转写 → 内容/流利度/发音评估 | 🆕 P2（需本地音频栈）|
| **听力训练（Listening, Paper 3）** | 本地 TTS 生成音频 + 理解题 + 批改 | 🆕 P2 |

### 簇 C — 诊断与自适应（Diagnostic & Adaptive）

| 工具 | 说明 | 状态 |
|------|------|------|
| **弱项诊断（Diagnostic Test）** | 短测快速定位知识盲点，产出能力画像 | 🆕 P1 |
| **个性化练习路径（Adaptive Path）** | 依诊断结果推送针对性练习序列 | 🆕 P2 |
| **限时模考（Timed Mock）** | 真实考试计时 + 交卷自动批改 + 报告 | 🆕 P1 |

### 簇 D — 复习与记忆（Review & Retention）

| 工具 | 说明 | 状态 |
|------|------|------|
| 间隔重复 FlashDeck | 已有 | ✅ |
| **错题本（Mistake Notebook）** | 自动归集错题、按知识点聚类、定期重练 | 🆕 P1 |
| **概念图/知识点串讲** | 由 KB 生成某主题的概念图与精讲 | 🆕 P2 |

### 簇 E — 学科覆盖扩展（更多 DSE 科目）

当前仅中/英/数。可逐步扩展（每科复用「出题 + 批改 + 专题」三件套模板）：

- **理科**：物理、化学、生物（实验题、计算题、官方 marking scheme 丰富，适合展示 RAG 批改）
- **商科/社科**：经济、BAFS、ICT
- **人文**：通识/公民与社会发展、历史、地理、中国历史

> 建议先补 **1 个理科**（如物理/化学）作为「结构化长题 + 官方 marking scheme 批改」的旗舰示范，最能体现 proposal 价值。

### 簇 F — 报告与分析（Reports & Analytics）

| 工具 | 说明 | 状态 |
|------|------|------|
| **学生表现报告** | 聚合历次成绩、强弱项雷达、趋势、建议，导出 PDF（交付物 #8）| 🆕 P1 |
| **教师班级面板** | 班级整体掌握度、共性错误、难点热力图 | 🆕 P2（教师向）|
| **学习进度追踪** | 个人 dashboard：练习量、正确率曲线、复习到期提醒 | 🆕 P2 |

---

## 六、建议的实施路线图

```
阶段 1（地基，1–2 周）   G1 本地 MLX 切换 + G4 历年试卷/marking scheme 入库
阶段 2（核心价值，2–3 周）G3 官方标准+CoT 批改 + G2 深度 RAG 接地（重构现有 9 个工具）
阶段 3（闭环增强）        簇 C 弱项诊断/限时模考 + 簇 D 错题本 + 簇 F 学生表现报告(交付物#8)
阶段 4（广度）           簇 E 扩 1 个理科（旗舰示范）+ 簇 A 整卷模拟/真题改编
阶段 5（进阶）           簇 B 口语/听力（本地 ASR/TTS）+ 教师向工具
阶段 6（交付）           G7 Tauri/.dmg + G8 PyInstaller 打包
```

**优先级心法**：先把「本地化 + RAG 接地 + 官方标准批改」这三根支柱补上（让现有 9 个工具达到 proposal 质量），再横向扩工具数量。否则即使加更多工具，也只是更多「云端 LLM 薄封装」，无法体现 proposal 的核心创新。

---

## 附录：关键文件索引

- 前端 Market 页：`web/app/(utility)/market/page.tsx`
- 前端 API 客户端：`web/lib/market-api.ts`，类型：`web/types/market.ts`
- 后端路由：`deeptutor/api/routers/{paper_forge,exam_grader,flash_deck,hkdse_chinese,hkdse_english,hkdse_maths}.py`
- 路由注册：`deeptutor/api/main.py:377-394`
- LLM 服务：`deeptutor/services/llm/{local_provider,cloud_provider,config}.py`
- RAG 服务：`deeptutor/services/rag/service.py`
- 历年试卷：`HKDSE_Paper/{Chinese,English,Math}/`
- 当前 LLM 配置：`.env`（`LLM_BINDING=deepseek` → 需改本地）
