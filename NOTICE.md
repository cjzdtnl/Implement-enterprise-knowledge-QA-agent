# 第三方与来源说明

本项目自身代码采用 MIT（见 LICENSE）。没有复制或 vendoring 第三方实现。运行时通过 pip 安装的依赖保留各自许可；分发这些依赖时须遵守其随包许可证。

- rank-bm25 0.2.2：Apache-2.0，使用未修改的 BM25Okapi。
- Pydantic 2.12.5：MIT，结构与参数校验。
- HTTPX 0.28.1：BSD-3-Clause，HTTP 传输。
- pytest 9.0.2：MIT，测试。

版本均为本机实际安装结果；传递依赖快照见 requirements-lock.txt。实际阅读来源和未复制代码的范围详见 docs/04-ai-usage.md。合成公司资料、测试标签与项目实现由 AI 按本次需求生成，不能表述为真实公司数据或候选人独立完成的经历。
