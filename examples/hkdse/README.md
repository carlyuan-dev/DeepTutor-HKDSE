# HKDSE 小型体验材料

这些原创材料用于体验功能，不是官方试题、完整考纲或检索质量评测集。可按仓库 LICENSE 使用。它们不包含真实学生信息，也不需要 OCR。

| 知识库名称 | 只导入这个文件 | 可直接复制的检索问题 | 应能找到的依据 |
| --- | --- | --- | --- |
| `demo-hkdse-chinese` | [chinese/reading.txt](chinese/reading.txt) | 作者为什么不再只追求回家更快？他是否反对所有街道翻新？ | 避雨观察、社区照应、保留店铺并改善通行的建议 |
| `demo-hkdse-english` | [english/reading.txt](english/reading.txt) | Why did Harbour School change its spending plan, and how will it evaluate the repair afternoon? | 借用工具、购买耗材、一个月后检查及询问未参加者 |
| `demo-hkdse-maths` | [maths/quadratics.txt](maths/quadratics.txt) | x^2 - 6x + k = 0 有二重实根，怎样求 k？ | MATH-04，令判别式为零，k=9 |

不要把整个 examples 目录一并导入。`inputs/` 是手动粘贴到功能页面的输入，不是检索语料；本 README 中的体验提示也无需入库。

- 作文批改输入：[inputs/english-essay.txt](inputs/english-essay.txt)，是一篇短演示文，不代表完整考试长度。
- 数学 Agent 输入：`请先读取我的数学学习记录，再给我一道判别式的基础选择题。请用练习工具出题并等待我作答，暂时不要透露答案。`
- Learning Loop：选择数学示例库，主题填写 `一元二次方程：判别式与实根个数`，生成 3 道基础选择题，自行作答后批改。可以有意答错一题以观察薄弱项反馈；不要预设模型必定给出某个薄弱项。
- 英语口语：页面已内置四类原创话题，不必导入上述文件。

安装、配置及完整操作顺序见 [快速体验](../../docs/QUICKSTART.md)。
