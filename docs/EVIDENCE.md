# 测试与检索评测

三科客观题学习链的新增实现与验收见 [三科学习工具链验收](design/2026-09-30-multisubject-learning-validation.md)。下文历史数学验收保留原口径，不追溯改写为三科测试。

## 数学学习与工具协议

核心测试位于 `tests/services/learning/test_learning_chain.py`、`tests/agents/chat/test_learning_chain_flow.py`、`tests/api/test_learning_chain_market.py` 和 `tests/core/test_labeled_step_*.py`。分别验证评分服务、工具链与 API 以及动作标签边界；使用假模型的测试不证明模型自主决策质量。

已有集成运行记录覆盖读状态、出题、暂停作答、提交答案及同进程断线续答。运行记录未随仓库分发；离线测试与真实模型运行的验证范围不同。

## 口语与 Learning Loop

`web/tests/oral-practice-races.test.mjs` 执行页面实际控制函数，模拟过期回调、逆序完成、转场和部分转写变化；测试替换网络、时钟和语音环境，不等价于真实 ASR/TTS 验收。

`web/tests/learning-loop-context.test.mjs` 与 `tests/api/test_learning_loop_reading.py` 覆盖练习归属和阅读材料传递。确定性结果归属不保证模型批改本身正确。

## 中文 BM25 外部评测

基于 mMARCO 构建的冻结中文评测集包含 200 条查询、106,813 个段落。默认分词与字符 bigram 对照：MRR@10 从 0.057 到 0.481，Hit@5 从 6.5% 到 57.5%。这是中文词法失效修复，不是 mMARCO 官方榜单结果，也不证明 HKDSE 教学效果。

200 条查询沿用早期小池，后续方案冻结前已观察过 BM25 结果；不能称为新的独立未见查询测试。冻结语料和排名仍能支持可追溯的组件对照。

## HKDSE 领域评测

最终记录使用中英数各 50 条、共 150 条查询和 2,850 个文本块。它不同于早期 content-v2.1 的 150 条（75 dev／75 test、1,561 块）；早期 domain-v2/v3 及已使用来源属于开发曝光。最终标签经过排名后审计，不再描述为严格一次性未见测试。

| 方案 | MRR@10 | Hit@5 | Support@5 |
| --- | ---: | ---: | ---: |
| Dense | 0.516868 | 0.646667 | 0.706667 |
| 中文 BM25 | 0.459460 | 0.613333 | 0.686667 |
| 等权 RRF | 0.527889 | 0.700000 | 0.773333 |

以上采用 `semantic_explicit_evidence_patch_v4` 标签口径。MRR／Hit 要求单块完整支持；Support 允许前五块联合覆盖必要证据组。分母为全部 150 条，包含 115 条单块完整、15 条仅联合完整和 20 条未确认；未知不等于无答案。模型语义审核不是人类 gold。配对区间不足以证明 Hybrid 稳定胜过 Dense。

### 参数卡

- 历史 embedding：阿里云兼容接口 `text-embedding-v4`，返回 1,024 维；配置值 2,048 未实际发送；具体权重修订未记录。
- SentenceSplitter：token chunk 512、overlap 50；metadata 占用正文预算。
- Dense：归一化余弦；BM25：正文、Lucene、k1=1.5、b=0.75、保留正分；中文字符 bigram、英文词干、数字保留，不转繁简。
- 学科内检索；两分支各取 50，等权 RRF 为 Σ1/(60+rank)，输出 50，同分按 chunk_id；无 reranker。
- 单块相关与多块联合支持分别标注；历史实现与当前环境不冒充完整锁定的可重复实验镜像。

### 复现范围

检索实验与复算实现位于：

- `scripts/rag_full_corpus_bm25_validation.py`：BM25 对照、稳定排序及逐查询指标。
- `scripts/rag_full_corpus_hybrid_ablation.py`：Dense／BM25／RRF 消融与候选覆盖分析。
- `scripts/rag_full_corpus_bm25_verify.py`：从原始排名独立复算指标。

排序、融合、指标计算及 Parquet 读取的核心检查使用自包含的小输入，不需要 API 或历史语料：

```sh
python -m pytest -q tests/eval/test_rag_full_corpus_bm25_validation.py tests/eval/test_rag_full_corpus_hybrid_ablation.py tests/eval/test_rag_full_corpus_bm25_verify.py
```

这些检查验证实验实现，不是完整检索对照数据集。运行全量脚本需要下面列出的历史输入，混合检索实验还涉及配置的 Embedding 服务调用。

本仓库提供检索实现与离线单元测试，不包含第三方正文、运行缓存及原始评测排名。因此仅凭仓库内容不能复算上述历史大集数字；完整复现需要对应版本的语料、查询、标签和排名数据。使用其他数据集运行所得结果应单独报告，不与本页结果混用。
