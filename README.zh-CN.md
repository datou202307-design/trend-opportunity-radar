<p align="center">
  <img src="assets/github-hero.zh-CN.svg" alt="Trend Opportunity Radar——从平台信号找到下一步行动" width="100%">
</p>

<h1 align="center">Trend Opportunity Radar</h1>

<p align="center">
  面向 AI Agent 的证据型社交聆听与趋势研究：一个主题、一个平台、一个清晰的下一步判断。
</p>

<p align="center">
  <a href="https://github.com/datou202307-design/trend-opportunity-radar/releases"><img alt="发布版本" src="https://img.shields.io/github/v/release/datou202307-design/trend-opportunity-radar?include_prereleases&style=flat-square&label=release"></a>
  <img alt="5 个研究场景" src="https://img.shields.io/badge/research_scenarios-5-14b8a6?style=flat-square">
  <img alt="7 条平台研究路径" src="https://img.shields.io/badge/platform_routes-7-0f766e?style=flat-square">
  <img alt="输出 HTML、Markdown 和 JSON" src="https://img.shields.io/badge/outputs-HTML_%C2%B7_MD_%C2%B7_JSON-0369a1?style=flat-square">
  <a href="LICENSE"><img alt="MIT 许可证" src="https://img.shields.io/badge/license-MIT-334155?style=flat-square"></a>
  <a href="https://github.com/datou202307-design/trend-opportunity-radar/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/datou202307-design/trend-opportunity-radar?style=flat-square"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>简体中文</strong>
</p>

<p align="center">
  <a href="#不登录平台先跑通完整报告"><strong>运行合成 Demo</strong></a> ·
  <a href="#先看看最后会得到什么"><strong>查看合成报告</strong></a> ·
  <a href="#五种研究场景"><strong>选择研究场景</strong></a>
</p>

这是一个独立、去品牌化的 Agent Skill，可用于社交聆听、市场研究、竞品用户研究、内容机会分析和产品需求验证。你提供研究主题和目标平台，Agent 负责采集或导入信号、打开原文、检查反例，并生成帮助决策的本地报告。它可以研究产品，也可以研究一个商机、想法、用户问题、受众需求或项目。

### 为什么不只用一句搜索提示词？

| 常见的搜索总结 | Trend Opportunity Radar |
|---|---|
| 找到什么就总结什么 | 冻结一个主题、一个平台和有边界的采样计划 |
| 可能跳过原文，混淆事实与推断 | 打开来源，并区分平台事实、机器提取和模型判断 |
| 主要展示支持观点的例子 | 完整检查相关性、反例和证据边界 |
| 最后给出宽泛建议 | 生成本地 HTML、Markdown、JSON 和具体的下一项验证 |

当前版本是 **v0.13.0 candidate**。这一版新增免登录合成 Demo、两输入首次研究设置，以及可审计的安装包。它帮助你形成更有依据的下一步判断，不预测爆款、流量、需求或收入。兼容快照监测仍属于候选工作流，首次真实三天前向对比仍待完成。

## 不登录平台先跑通完整报告

内置 Demo 使用明确标注的合成证据，并与真实研究共用同一个报告生成器。它不会打开浏览器、读取平台，也不需要任何账号。

**Windows PowerShell**

```powershell
py -3 skills/trend-opportunity-radar/scripts/trend_radar.py demo --language zh-CN --output-dir ./trend-radar-demo
```

**Ubuntu、macOS 或其他 Python 3 环境**

```bash
python3 skills/trend-opportunity-radar/scripts/trend_radar.py demo --language zh-CN --output-dir ./trend-radar-demo
```

打开 `trend-radar-demo/trend-report.html` 即可查看。页面提示、Markdown、JSON 和运行清单都会说明这是合成演示，不是真实平台结论。

## 开始第一次研究

只需要两个输入：

1. 你想研究什么。
2. 你想研究哪个平台。

```text
使用 $trend-opportunity-radar，分析“帮助小网店减少重复售后回复的 AI 助手”在 X 平台的产品需求。
```

如果希望用两个输入确定性地开始，可以先生成请求文件，再启动正式研究：

```bash
python3 skills/trend-opportunity-radar/scripts/trend_radar.py init --topic "帮助小网店减少重复售后回复的 AI 助手" --platform x --language zh-CN --output-dir ./first-study
python3 skills/trend-opportunity-radar/scripts/trend_radar.py start --request ./first-study/research-request.json --output-dir ./first-study/run
```

如果没有指定研究目的，Agent 会结合你的问题推断；只有不同选择会明显改变结果时，才会请你确认。标准研究会尽量采集 60–100 条观察结果、保留 30–50 条去重信号、打开 12–18 条原文，并寻找至少 3 条反例。数据不足时不会用弱相关内容凑数。

## 五种研究场景

同一套证据工作流，可以根据你的目的回答五类不同问题。

<p align="center">
  <img src="assets/research-scenarios.zh-CN.svg" alt="五种研究场景：发现商业机会、监测品牌舆情、研究竞品用户、寻找内容机会和验证产品需求" width="100%">
</p>

<p align="center"><a href="https://datou202307-design.github.io/trend-opportunity-radar/zh-CN/"><strong>查看五个合成完整案例 →</strong></a></p>

| 你想解决的问题 | 研究会回答什么 | 主要产出 |
|---|---|---|
| 发现商业机会 | 哪些问题还没被解决，值得先试？ | 优先验证的机会 |
| 监测品牌舆情 | 大家在表扬、质疑或求助什么？ | 需要回应的议题 |
| 研究竞品用户 | 用户为什么留下、抱怨或切换？ | 可切入的用户问题 |
| 寻找内容机会 | 大家反复在问什么，下一篇先讲什么？ | 值得测试的内容方向 |
| 验证产品需求 | 用户真的需要它吗？最小先验证什么？ | 最小需求验证方案 |

## 先看看最后会得到什么

报告先给出直接回答，再展示本次采集数量、主要发现、原文依据、反例和下一步验证动作。下面只使用合成数据展示结构，不代表任何真实平台结论。

<p align="center">
  <img src="assets/report-preview.zh-CN.svg" alt="使用合成数据展示的趋势机会雷达本地报告" width="100%">
</p>

每次研究会生成：

- `trend-report.html`：适合直接阅读和分享的本地页面；
- `trend-report.md`：适合继续编辑或交给其他 Agent；
- `opportunities.json`：保留完整证据、评分和审计字段。

## 平台支持

| 平台或来源 | 当前状态 | 可以研究什么 | 本次运行要求 |
|---|---|---|---|
| X | 已验证 | 搜索结果、帖子原文和可见互动指标 | 通过本次只读能力检查 |
| 小红书 | 已验证 | 搜索卡片、内容详情和可见互动指标 | 已授权的浏览器或结构化导入 |
| YouTube | 已验证 | 搜索、视频详情、有限评论和按需字幕 | 公开内容；评论与字幕按可用性读取 |
| Reddit | 已验证 | 社区发现、帖子搜索和详情核对 | 用户连接第三方 MCP；评论树暂不读取 |
| Instagram | Hashtag 主题研究已验证 | Hashtag 内容、详情和有限可见评论 | 已登录且已授权的浏览器会话 |
| Facebook | Posts 主题研究 Beta | 公开 Posts 搜索、详情核对和有限可见评论 | 显式启用且已授权、已登录的浏览器会话 |
| TikTok | 主题研究 Beta | 主题搜索、视频详情和有限评论补充 | 显式启用且已登录的 Chrome 会话 |
| JSON / CSV | 通用导入 | 用户提供的结构化信号 | 不需要实时连接器 |

Instagram 已知账号研究仍是独立试点，不等于主题研究能力。TikTok 匿名实时研究不在支持范围内；抖音尚未通过独立真实验收。任何平台在每次运行时都要重新检查当前可用能力，不能仅凭已经安装工具或浏览器已经登录就假定可用。

## 它如何工作

1. **说清问题**：把自然语言请求整理为一个主题、一个平台和一个业务问题。
2. **采集信号**：读取公开或已授权内容，保存来源、时间、互动指标和采集记录。
3. **核对证据**：去重、打开原文、检查相关性、反例和数据缺口。
4. **给出建议**：输出当前可以判断什么、依据是什么，以及下一步验证什么。

观察热度和证据可靠性始终分开。搜索卡片不会因为互动高就自动成为结论；视频字幕、机器转写和 OCR 也会分别标明来源，不会改写成平台事实。

## 安装

把 Skill 目录复制到你的 Agent Skill 目录：

```text
skills/trend-opportunity-radar/
```

在 Codex 中，把 `trend-opportunity-radar` 放到 `$CODEX_HOME/skills/`，然后重新加载 Agent 会话。其他 Agent 可以适配 `SKILL.md`、参考契约和 Python 脚本。内置脚本只使用 Python 标准库，建议使用 Python 3.10 或更高版本。

从 v0.13 开始，正式发布会在 [Releases 页面](https://github.com/datou202307-design/trend-opportunity-radar/releases)附带可安装 ZIP、SHA-256 校验文件和完整清单。压缩包内只有一个可直接复制到 Agent Skill 目录的 `trend-opportunity-radar/` 文件夹，不包含测试、缓存、本机输出、凭据、浏览器会话或真实平台数据。

也可以使用确定性的统一入口冻结请求，并且一次只返回一个下一动作：

```bash
python skills/trend-opportunity-radar/scripts/trend_radar.py start \
  --prompt "分析 AI 旅行规划在 X 平台的内容机会。" \
  --output-dir ./trend-research/ai-travel-x

python skills/trend-opportunity-radar/scripts/trend_radar.py doctor \
  --platform x \
  --language zh-CN

python skills/trend-opportunity-radar/scripts/trend_radar.py resume \
  --run-dir ./trend-research/ai-travel-x
```

`doctor` 不会安装工具或修改登录状态。只有该平台实际使用的只读预检成功后，实时路径才会显示可用；否则仍可以使用结构化数据导入。每完成一个阶段后调用 `resume`：它会自动执行安全的确定性步骤、保存不可变阶段收据，并在实时采集、模型判断或视觉验收边界停下；只有运行清单进入 `complete` 才表示报告真正完成。

如果需要持续观察，可以把一次已完成研究冻结为监测基线，追加后续兼容快照，再生成三种格式的时间对比：

```bash
python skills/trend-opportunity-radar/scripts/trend_radar.py monitor create --run-dir ./run-1 --monitor-dir ./monitor
python skills/trend-opportunity-radar/scripts/trend_radar.py monitor append --monitor-dir ./monitor --run-dir ./run-2
python skills/trend-opportunity-radar/scripts/trend_radar.py monitor compare --monitor-dir ./monitor
```

默认观察四次：X/TikTok 每三天一次，其他平台每周一次。命令会保存监测状态和建议频率，但未获得用户明确确认且外部定时任务未真实创建成功前，不会声称已经安排监测。快照变化只表示两次采集中可见信号的差异，不等于需求增长或未来表现。

### 在一个本地工作区继续历史研究

当你已经有多项研究或监测周期时，可以生成本地索引：

```bash
python skills/trend-opportunity-radar/scripts/trend_radar.py workspace --root ./trend-research --output-dir ./trend-research/workspace --language zh-CN
```

打开 `trend-research/workspace/index.html`。页面会分开显示尚未结束的研究、已经到期的复采建议、已完成报告和持续观察周期，并为每项行动提供可以直接交给 Agent 的继续用语；同时生成可选的本地摘要卡。工作区不会上传研究内容、暴露绝对路径，也不会把建议频率写成已经创建的定时任务。

## 数据访问与隐私

Skill 可以使用用户上传的 JSON/CSV、公开网页、受控只读浏览器、已授权 API 或历史快照。Chrome、OpenCLI、DokoBot 和第三方 MCP 都是可选适配器，不随仓库分发。

- 只读取公开或明确授权的数据；
- 不打包 Cookie、Token、浏览器会话或客户数据；
- 不并发执行高频浏览器操作；
- 遇到验证码、限流或访问控制时停止，而不是尝试绕过；
- 当前环境缺少适配器时，可以改用结构化数据导入。

用户需要自行遵守平台条款、账号权限和适用法律。

## 它不会声称什么

- 不把单次研究写成正在上升或下降的长期趋势；
- 不把互动量直接解释为需求、收入或商业吸引力；
- 不混合不同平台的热度评分；
- 不把搜索卡片、机器转写或模型推断伪装成平台事实；
- 不在采样不足时用低相关内容凑满报告；
- 不宣称能够预测未来爆款、流量、需求或收入。

## 方法和适配器文档

- [采样合同](skills/trend-opportunity-radar/references/sampling-contract.md)
- [统一执行入口](skills/trend-opportunity-radar/references/execution-cli.md)
- [本地研究工作区](skills/trend-opportunity-radar/references/workspace.md)
- [评分合同](skills/trend-opportunity-radar/references/scoring-contract.md)
- [平台适配器](skills/trend-opportunity-radar/references/platform-adapters.md)
- [浏览器采集](skills/trend-opportunity-radar/references/browser-collection.md)
- [视频证据](skills/trend-opportunity-radar/references/video-evidence-contract.md)
- [输出结构](skills/trend-opportunity-radar/references/output-schema.md)

## 第三方兼容性

DokoBot、OpenCLI、Chrome、mcp-video-analyzer、yt-dlp、whisper-ctranslate2、X、小红书、YouTube、Reddit、TikTok、Instagram 和 Facebook 均为可选第三方工具或平台。名称仅用于说明兼容或研究目标，不代表关联、背书、账号访问或授权。

## 仓库结构

```text
skills/trend-opportunity-radar/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
├── references/
└── tests/
```

## 发布安全

仓库只包含合成测试夹具和示意资产，不包含真实平台采集数据、浏览器会话、凭据、客户材料、内部品牌或本机运行产物。发布前运行：

```text
python tools/audit_open_source_release.py
python tools/validate_skill.py skills/trend-opportunity-radar
python -m unittest discover -s skills/trend-opportunity-radar/tests -v
```

维护者可以保存仅包含仓库级数据的私有 GitHub Traffic 快照，不需要给 Skill 增加遥测：

```text
python tools/snapshot_github_traffic.py --repo owner/name --output-dir ../private-github-traffic
```

命令只读取当前 GitHub 身份有权查看的仓库指标；同一天重复运行默认跳过，API 出错时不会写入半成品，并明确记录 clone 不等于已验证的安装或用户。真实 Traffic 快照不要提交到这个公开仓库。

## 许可证

MIT License，见 [LICENSE](LICENSE)。
