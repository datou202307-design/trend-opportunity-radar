<p align="center">
  <img src="assets/github-hero.zh-CN.svg" alt="趋势机会雷达——为 AI Agent 提供有证据边界的平台研究" width="100%">
</p>

<h1 align="center">Trend Opportunity Radar</h1>

<p align="center">
  把平台信号转化为可审查的商业、品牌、竞品用户、内容和产品需求决策。
</p>

<p align="center">
  <a href="https://github.com/datou202307-design/trend-opportunity-radar/releases"><img alt="发布版本" src="https://img.shields.io/github/v/release/datou202307-design/trend-opportunity-radar?include_prereleases&style=flat-square&label=release"></a>
  <img alt="5 个决策模式" src="https://img.shields.io/badge/decision_profiles-5-14b8a6?style=flat-square">
  <img alt="平台：X、小红书、YouTube 和 TikTok Beta" src="https://img.shields.io/badge/platforms-X_%2B_Xiaohongshu_%2B_YouTube_%2B_TikTok_Beta-0f766e?style=flat-square">
  <img alt="输出：HTML、Markdown 和 JSON" src="https://img.shields.io/badge/outputs-HTML_%C2%B7_MD_%C2%B7_JSON-0369a1?style=flat-square">
  <a href="LICENSE"><img alt="MIT 许可证" src="https://img.shields.io/badge/license-MIT-334155?style=flat-square"></a>
  <a href="https://github.com/datou202307-design/trend-opportunity-radar/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/datou202307-design/trend-opportunity-radar?style=flat-square"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>简体中文</strong>
</p>

这是一个独立、去品牌化的 Agent Skill，用于在单个平台上围绕一个研究主题完成有证据边界的趋势机会研究。

当前状态：**v0.9.0 candidate**。它是一套受约束的平台研究工作流，不是爆款、流量、需求或收入预测系统。候选版支持在 X、小红书和 YouTube 上使用五种决策模式，并为用户授权且已登录的 Chrome 会话提供需显式启用的 TikTok 主题研究 Beta。OpenCLI 只读采集及 DokoBot 渲染页面核验或回退，仅在当前环境通过能力探测时使用。

## 它能做什么

- 接受产品、商机、想法、用户问题、受众需求或项目作为研究主题。
- 支持五类决策目标：发现商业机会、监测品牌舆情、研究竞品用户、寻找内容机会和验证产品需求。
- 把简短自然语言请求编译成带版本的研究上下文，用户无需填写内部证据角色或采样门槛。
- 每次只分析一个平台，包括 X、小红书、YouTube、显式启用的 TikTok Beta 及符合适配器契约的其他平台。
- 导入用户提供的数据，或采集已授权的只读浏览器和 API 信号。
- 规范化证据、来源链接、采集时间、指标和局限。
- 使用明确的快速、标准和深度采样契约，并保留采集账本。
- 把每次完成的查询原子写入唯一的原始快照。
- 编排与适配器无关的查询推进、原始输出留存、有限恢复和采样门槛。
- 区分读取成功、超时、仍可继续和明确穷尽；首屏完成或单次超时不能再被当作查询已穷尽。
- 通过确定性包装器记录 DokoBot 仅在控制台可见的会话信息，保留不可变采集审计文件，并对失效续采执行一次重启。
- 在采集前诊断 DokoBot 缺失、沙箱不可见、权限不足、损坏或浏览器断连等环境状态。
- 分离观察热度与证据置信度，并明确呈现缺失数据。
- 降低未打开搜索卡片的证据等级，并限制不完整采集的置信度。
- 跨搜索卡片和详情页去重同一平台内容，同时保留查询和来源轨迹。
- 对每个证据层执行观察量、去重量、详情量、语义相关性和主题连接门槛。
- 聚类主题成为可审查结论前，要求显式、可审计的语义聚类计划。
- 把零结果查询保留为可审计账本记录，并拒绝从进行中的采集状态渲染报告。
- 在剩余采集预算内，为不足证据层生成简短、不重复的恢复查询。
- 排除审查失败的聚类和重复机会卡，不为视觉数量凑数。
- JSON 保留完整审计状态；面向人的报告使用本地化研究状态说明，而不是软件报错。
- 把逐条限制说明压缩为最多四条对决策有影响的摘要，同时在 JSON 保留完整列表。
- 推荐可选、可迁移的后续监测任务，让单次快照逐步形成可比较时间序列，但不会假装已创建自动任务。
- 保留每次重复原始采集为独立尝试文件，不覆盖早期证据。
- 根据用户目的、研究目标和受众调整报告语言与决策框架，并为可见证据缺口提供当前价值、边界和解决路径。
- 在报告前回填可用详情链接，不消耗搜索查询预算，也不向用户暴露可恢复的内部采样门槛。
- 使用大众可理解的标题检查，保留审计标题，同时用具体表达替换未解释的产品行话。
- 生成主题与研究对象的结合机会、反向证据、风险、验证动作和复采任务。
- 明确区分平台事实、用户前提、模型推断和人工确认。
- 输出自包含本地 HTML、精简 Markdown 和机器可读 JSON。
- 拒绝疑似乱码，并验证 HTML、Markdown 和 JSON 来自同一份一致的 UTF-8 结果。
- 对视频承载主要信息的平台，先用搜索卡发现候选，再对最多 10 条去重代表视频执行可选的字幕、语音、关键帧和 OCR 证据解析；视频片段不会增加趋势样本数。

## 最少输入

只需要两个输入：

1. 一个可以理解的研究主题。
2. 一个目标平台。

示例：

```text
使用 $trend-opportunity-radar，分析“帮助餐厅填补临时空桌的 AI 助手”在 X 平台的趋势机会。
```

通用调用：

```text
分析研究主题在某平台的趋势机会。
```

Agent 应在安全的情况下推断语言、地区、受众、查询词、时间窗、来源模式、采集方式和输出路径。标准研究以 60–100 条观察结果卡、30–50 条去重保留信号、12–18 个已打开详情和至少 3 条反向信号为目标。这些目标用于提高可复现性，不能用弱证据凑数。

## 安装

把 Skill 目录复制到 Agent 的 Skill 目录：

```text
skills/trend-opportunity-radar/
```

在 Codex 中，把 `trend-opportunity-radar` 放到 `$CODEX_HOME/skills/`，然后重启或重新加载 Agent 会话。其他 Agent 可以把 `SKILL.md`、参考契约和 Python 脚本适配到自己的 Skill 或工具格式。

内置脚本只使用 Python 标准库，建议使用 Python 3.10 或更高版本。

## 数据访问

工作流不强制依赖实时数据连接器，支持：

- 用户上传的 JSON 或 CSV；
- 公开网页信号；
- 受控的只读浏览器采集；
- 已授权的平台 API；
- 历史快照。

Chrome、OpenCLI、DokoBot 或等效受控浏览器均为可选项。适配器选择器只使用经过验证的只读能力；当采样量不足时会阻止交付，而不是静默降级。用户需要自行遵守平台条款、账号权限和合法数据访问要求。任何凭据、Cookie 或 Token 都不得写入 Skill 的输入或输出。

在 YouTube 上，已验证路径覆盖有限搜索、视频详情补充和单独发起的有限评论读取。每个符合条件的视频最多保留 10 条代表性评论；字幕只在需要核验视频主张时打开。支持某个平台不代表评论、字幕或当前浏览器登录状态一定可用，每次运行仍必须先通过本次只读能力探测。

### 可选视频证据运行时

TikTok 等视频信息流可使用试验性的 `video-evidence-contract-v0.1`：搜索适配器负责发现和去重，独立视频解析层负责原生字幕、本地 ASR、关键帧和画面 OCR。各通道分别标记来源，不把机器转写或 OCR 写成平台事实。

TikTok 主题研究 Beta 只在明确启用、用户授权且已经登录的 Chrome 会话中可用。OpenCLI 负责有限主题搜索，另行通过预检的 DokoBot 浏览器会话补充代表内容详情；若目标详情已核对但 DokoBot 没有返回评论正文，内置的两段式记录器会先冻结唯一目标，再让可用的 Chrome 控制适配器只展开一次该目标的评论入口。记录器会核对请求哈希、内容 ID、作者路径、数量上限和无写操作声明，全部通过后才合并最多 5 条真实可见顶层评论。页面评论总数与实际采集正文数量分开，评论补充失败不阻断已经完成的搜索与详情报告。

参考 Runner 可配合固定版本的 [mcp-video-analyzer](https://github.com/guimatheus92/mcp-video-analyzer)、[yt-dlp](https://github.com/yt-dlp/yt-dlp) 和可选的本地 [whisper-ctranslate2](https://github.com/Softcatala/whisper-ctranslate2) 使用。这些依赖均不随仓库分发。先运行 `scripts/check_video_evidence_runtime.py`；Windows 建议使用隔离目录中的固定本地入口，不要在每条视频上重复执行临时 `npx` 安装。

Beta 默认只接受公开或明确授权的单条视频 URL，最大并发为 1，删除临时帧，不保留完整媒体，不转发 Cookie、浏览器会话、云端语音 API Key 或 Hugging Face Token。TikTok 匿名实时研究不在支持范围内，结构化导入仍是不依赖会话的降级路径；抖音视频解析尚未通过真实验收，不能据此宣称支持。

可用的媒体文本必须先由 Agent 完成语义复核，才会进入报告。HTML/Markdown 只显示少量经过复核的原文摘录，并明确区分视频字幕、机器语音转写和机器画面文字；原始 ASR/OCR 只保留在 JSON 审计数据中，不要求用户逐条标注。

## 重要边界

- 不混合不同平台的热度评分。
- 浏览器采集的 X 数据必须标记为受控采集，不能标记为 API 数据。
- 没有可比较时间序列时，使用“信号快照”，不要声称趋势方向。
- 采样契约未完成时，不把机会标记为 `review_ready`。
- 任一查询层质量门槛失败时，不能用全局总量替代分层门槛。
- 证据置信度不等于商业吸引力；不能从单次快照推断趋势方向。
- 不在 `raw-signals.json` 之外维护第二份手工采集账本。
- 产品按事实约束对象处理；想法和商机按待验证假设处理。
- 只有人工可以把 `review_ready` 证据升级为 `confirmed`。
- 不宣称证据热度指数能够预测未来爆款、流量、需求或收入。

## 第三方兼容性

DokoBot、OpenCLI、Chrome、mcp-video-analyzer、yt-dlp、whisper-ctranslate2、X、小红书、YouTube 和 TikTok 都是可选的第三方工具或平台，不随本仓库分发。名称仅用于说明兼容或试验目标，不代表关联、背书、账号访问或授权。只在具有合法访问权限并遵守适用条款时使用相应集成。

## 仓库结构

```text
skills/trend-opportunity-radar/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
├── references/
└── tests/
```

## 许可证

MIT License，见 [LICENSE](LICENSE)。

## 发布安全

仓库只包含合成测试夹具，不打包平台采集数据、浏览器会话、凭据、客户材料、内部品牌或本机运行产物。发布变更前运行：

```text
python tools/audit_open_source_release.py
python tools/validate_skill.py skills/trend-opportunity-radar
python -m unittest discover -s skills/trend-opportunity-radar/tests -v
```
