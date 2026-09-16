<h1 align="center">BossHunter Improved</h1>

<p align="center">
  基于 BossHunter 的本地智能求职 Agent 改进版：围绕岗位采集、AI 评分、预投递、简历中心和模板渲染进行二次开发。
</p>

<p align="center">
  <a href="https://github.com/T-zero112/BossHunter-improved"><img alt="Project" src="https://img.shields.io/badge/project-BossHunter--improved-FB6511"></a>
  <a href="https://www.python.org/"><img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="https://github.com/T-zero112/BossHunter-improved"><img alt="License" src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue"></a>
  <a href="https://github.com/T-zero112/BossHunter-improved/commits/main"><img alt="Last Commit" src="https://img.shields.io/github/last-commit/T-zero112/BossHunter-improved"></a>
</p>

<p align="center">
  本地运行 · 人工确认 · AI 解析 · 预投递管理 · 简历模板渲染
</p>

**BossHunter Improved** 是我在原 BossHunter 基础上做的一版求职自动化产品改进项目。项目目标不是简单完成自动投递，而是把“岗位发现、岗位评估、投递前准备、简历结构化管理、针对岗位生成简历和沟通语”串成一个更适合个人求职场景的本地工作台。

本仓库是一个学习和作品展示项目，重点体现我对 AI Agent 产品流程、前后端协作、简历结构化解析、自动化安全边界和模板渲染工程化的理解。所有投递相关动作都保留人工确认，不追求绕过平台限制或提高发送频率。

[原项目 BossHunter](https://github.com/shengjidaguai-china/BossHunter) · [完整上手指南](docs/QUICKSTART.md)

> [!WARNING]
> 自动化操作招聘平台存在账号限制或封禁风险。本项目仅供学习、研究和个人求职效率提升；请遵守平台规则，保持低频，并自行承担使用风险。项目与任何招聘平台及其关联公司不存在隶属、合作或背书关系。

## 改进重点

| 模块 | 改进内容 |
|---|---|
| 预投递工作台 | 增加固定预投递区域，支持查看待发送岗位、重新生成招呼语、发送窗口提示和定时投递任务设计 |
| 招呼语生成 | 按“基本情况 + JD 相关项目经验 + 其他匹配内容”的结构生成，更强调实事求是和岗位相关性 |
| 简历中心 | 从上传完整简历扩展为可编辑的结构化简历资料库，支持个人信息、教育背景、项目经历、学术成果、校园与实践经历、荣誉奖项、技能证书、综合评价等模块 |
| 简历解析 | 针对 PDF/DOCX 导入做多轮修正，引入更明确的归类边界、标题识别、经历说明整理和 AI 辅助解析思路 |
| 富文本编辑 | 将原本简单的按钮样式升级为更接近真实编辑器的富文本编辑能力，支持常用排版操作 |
| 模板中心 | 增加可视化模板卡片，接入 Reactive Resume 和 RenderCV 模板资源，并探索源码级模板渲染适配 |
| 安全与隐私 | 本地配置、个人数据、密钥文件、虚拟环境和依赖目录默认不进入 Git 仓库 |

## 技术亮点

- 基于 Python 后端和 React/Vite 前端构建本地 Web 工作台。
- 使用本地浏览器自动化连接招聘平台，投递动作保留人工确认。
- 通过 AI 对岗位 JD、简历信息和沟通语进行结构化处理。
- 针对简历导入场景设计“规则解析 + AI 解析层 + 用户可编辑修正”的流程。
- 将外部简历模板资源接入模板中心，并尝试复用模板源码完成真实 PDF 渲染。
- 保留较完整的单元测试，便于持续验证简历中心、配置、采集、评分和 Web API 行为。

## 本仓库与原项目关系

本项目基于 BossHunter 进行二次开发，原项目采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。本仓库继续保留该许可证和非商业使用边界。外部模板来源、许可证与归属说明见 [NOTICE](NOTICE)。

本仓库不包含本地运行时的敏感文件，例如：

- `config.yaml`
- `.config.credentials.yaml`
- `data/`
- `.venv/`
- `node_modules/`
- 前端构建产物 `dist/`

## 核心能力

| 能力 | 说明 |
|---|---|
| 多平台岗位池 | 串行采集 BOSS 直聘、智联招聘和前程无忧 51job，支持来源去重 |
| AI 评分与筛选 | 先做关键词预筛，再结合岗位 JD 深度评分 |
| 人工确认 | 投递前必须审核，支持逐个或批量确认 |
| 个性化沟通 | 根据岗位 JD 和个人简历，为已确认岗位生成招呼语 |
| 保守发送 | 随机间隔、时间窗口、每日上限和发送前浏览 |
| 工作台与跟进 | 管理岗位、投递状态和 HR 回复 |
| 定制化简历 | 识别 HR 的简历请求，并结合岗位 JD 辅助生成定制化简历 |

### 平台能力边界

| 平台 | 采集与 AI 处理 | 投递与监听 |
|---|---|---|
| BOSS 直聘 | 支持 | 人工确认后低频发送，并支持回复监听 |
| 智联招聘 | 支持只读采集、评分和招呼语准备 | 在原平台手动投递，再回填“已发送” |
| 前程无忧 51job | 支持只读采集、评分和招呼语准备 | 在原平台手动投递，再回填“已发送” |

三个平台严格串行采集。检测到验证码、频率限制、登录墙或未知页面结构时会安全停止，不尝试绕过。

## 项目结构图

<a href="https://shengjidaguai-china.github.io/BossHunter/architecture/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/architecture/bosshunter.dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/architecture/bosshunter.light.png">
    <img alt="BossHunter 项目结构图：工作台、任务编排、AI、多平台采集、人工确认与浏览器执行。点击打开交互版。" src="docs/architecture/bosshunter.light.png" width="100%">
  </picture>
</a>

**[点击打开交互结构图 ↗](https://shengjidaguai-china.github.io/BossHunter/architecture/)** · [可编辑源文件](docs/architecture/bosshunter.architecture.json)

交互版支持缩放、节点搜索、关系追踪、深浅主题切换和图片导出。由 [Archify](https://github.com/yuppiez99999/archify-) 生成。

## 快速开始

需要 Python 3.10+、Node.js 22+、最新版 Google Chrome 和可用的 AI API。第一次使用按以下顺序操作：

```bash
git clone https://github.com/shengjidaguai-china/BossHunter.git
cd BossHunter
pip install -e .
bosshunter web
```

在本地打开的 `http://127.0.0.1:8686` 面板中上传本人的真实简历，设置岗位条件，并连接 AI 服务。API Key 只在本地面板输入，不要发送到聊天、Issue 或提交文件中。

随后开启 Chrome 远程调试，在同一个 Chrome 窗口登录招聘平台，再检查并运行：

```bash
bosshunter ai-status
bosshunter connect
bosshunter run
```

`bosshunter connect` 只检查连接，不会替你启动 Chrome 或登录招聘平台。Windows、macOS、Linux 的 Chrome 设置和完整排错步骤见 [完整上手指南](docs/QUICKSTART.md)。

## 文档导航

| 文档 | 内容 |
|---|---|
| [完整上手指南](docs/QUICKSTART.md) | 安装、Chrome 连接、首次配置和安全边界 |
| [CLI 命令](docs/CLI.md) | 一键流程、分步命令、监听与状态查看 |
| [配置指南](docs/CONFIGURATION.md) | 平台、AI、简历和风险控制配置 |
| [常见问题](docs/FAQ.md) | 封号风险、平台边界、简历格式和连接排错 |
| [贡献指南](CONTRIBUTING.md) | Issue、PR、开发与维护者申请 |
| [项目治理](GOVERNANCE.md) | 模块责任、权限、晋升与统计口径 |

## 版本更新

| 日期 | 版本号 | 类型 | 更新内容 |
|---|---|---|---|
| 2026-09-01 | v2.3.2 | 采集与简历稳定性 | 完成 51job API 只读采集的安全整合和真实环境验证；修复智联登录误判、单平台阻断后续任务和中文 PDF 简历乱码。 |
| 2026-08-25 | v2.3.1 | 多平台与安全整合 | 合入智联/51job 只读采集、外部平台人工投递闭环、岗位池与筛选增强、Windows 兼容、招呼语与消息判定修复，并重整 BOSS 页面访问保护设置。 |

完整版本历史、升级说明和验证记录见 [CHANGELOG.md](CHANGELOG.md)。

## 🧭 现任维护者

包括项目负责人在内的 5 名正式维护者共同维护全项目，不设置固定模块；擅长方向仅用于协作参考。

| GitHub | 身份 | 贡献占比 | 擅长方向 | 任期 |
|---|---|---|---|---|
| [@yukinoshi](https://github.com/yukinoshi) | 正式维护者（Write） | 26.2%（试算） | AI、错误恢复与产品流程 | 2026-08-29 起 |
| [@fengziliang43-cmyk](https://github.com/fengziliang43-cmyk) | 正式维护者（Write） | 25.4%（试算） | 运行时、发送安全与监测链路 | 2026-08-30 起 |
| [@yuppiez99999](https://github.com/yuppiez99999) | 正式维护者（Write） | 25.4%（试算） | 平台采集、城市数据与测试 | 2026-08-29 起 |
| [@bianshilong0604](https://github.com/bianshilong0604) | 正式维护者（Write） | 23.0%（试算） | Web、产品流程与隐私边界 | 2026-08-30 起 |
| [@powerycy](https://github.com/powerycy) 跑跑蹦蹦跳跳 | 项目负责人兼正式技术维护者（Admin） | 不参评 | 全仓技术审核、安全复核与合并；贡献文档与评分 | 项目发起至今；2026-09-06 起计入技术审核池 |

截至 **2026-09-07 14:00（Asia/Shanghai）**，以上为经项目负责人确认的试算结果。维护贡献与项目贡献分别记录；0604 的审核团队邀请尚待接受。

[查看维护者任期](MAINTAINERS.md) · [查看维护贡献及评分](MAINTENANCE_CONTRIBUTIONS.md) · [查看技术审核规则](GOVERNANCE.md)

技术 PR 的审核、测试验证与合并由包括项目负责人在内的正式维护者完成，项目负责人的有效批准按一人计入；本人提交或参与编写的技术改动不得自审计票，高风险 PR 仍需两名不同的非作者维护者批准。项目负责人负责 PR 项目贡献和维护贡献两类文档，并单方面决定维护贡献评分；本页摘要由维护者按贡献文档同步。

## 🔥 近 30 天贡献榜 Top 10

统计窗口：**2026-08-09 至 2026-09-07（Asia/Shanghai）**；实际核对截至 **9 月 7 日 14:00**。只计算该窗口内被主线采纳的部分，同分并列。

| 排名 | 贡献者 | 本期主要贡献 |
|:---:|---|---|
| 🥇 | [@yuppiez99999](https://github.com/yuppiez99999) | BOSS、51job 与猎聘采集回归；智联 API 与过滤链；三平台续采、城市快照及前端构建交付 |
| 🥈 | [@shuaigechz-cloud](https://github.com/shuaigechz-cloud) | 会话送达、消息方向与招呼语约束；母版项目保留、PNG/PDF 定制简历预览和显式人工确认 |
| 🥈 | [@zhenian-666](https://github.com/zhenian-666) | 多范围岗位导出、城市目录、回收站与独立 AI 评分；统一平台采集架构和智联只读采集 |
| 4 | [@yukinoshi](https://github.com/yukinoshi) | 多 AI 兼容、评分 JSON、错误恢复、凭据优先级与批次删除保护 |
| 5 | [@fengziliang43-cmyk](https://github.com/fengziliang43-cmyk) | 监测回复轮次、安全操作、本地凭据与面板交互；猎聘临时失败/保存失败保留断点的共同实现 |
| 6 | [@haohao-fly](https://github.com/haohao-fly) | 岗位筛选、分页与统计；结构化评分、失败重试、投递队列和任务保护 |
| 7 | [@hdfhssg](https://github.com/hdfhssg) | 学历与招聘类型筛选、评分上下文、岗位池排序、投递队列和额度提示 |
| 7 | [@meixiaoxie](https://github.com/meixiaoxie) | 配置原子写入与无凭据下载；公司屏蔽、城市查询与 Windows 回归测试 |
| 9 | [@Hebuyu688](https://github.com/Hebuyu688) | AI 诊断和模型别名解析、薪资区间过滤、招呼语正向依据与毕业届别校验 |
| 10 | [@yuj-029](https://github.com/yuj-029) | 51job 页面研究、只读采集核心、API 采样与断点续采实现 |

## 🏆 贡献总榜 Top 10

数据快照：**2026-09-07 14:00（Asia/Shanghai）**。只统计实际进入主线的外部人类贡献，按完整榜的四维影响评分归一化；同分并列，不按提交次数或代码行数排名。

| 排名 | 贡献者 | 贡献度 | 主要贡献方向 |
|:---:|---|:---:|---|
| 🥇 | [@yuppiez99999](https://github.com/yuppiez99999) | **10.0%** | BOSS、51job 与猎聘采集回归；智联 API 与过滤链；三平台续采、城市快照及前端构建交付 |
| 🥈 | [@shuaigechz-cloud](https://github.com/shuaigechz-cloud) | **7.9%** | 会话送达、消息方向与招呼语约束；母版项目保留、PNG/PDF 定制简历预览和显式人工确认 |
| 🥈 | [@yukinoshi](https://github.com/yukinoshi) | **7.9%** | Thinking 与多 AI 兼容；评分 JSON、错误传播、暂停恢复和凭据优先级；评分期间删除岗位不中断批次 |
| 🥈 | [@zhenian-666](https://github.com/zhenian-666) | **7.9%** | 多范围岗位导出、城市目录、回收站与独立 AI 评分；统一平台采集架构和智联只读采集 |
| 5 | [@GioiaZheng](https://github.com/GioiaZheng) | **6.8%** | API Key 脱敏与安全读取；PDF 依赖降级；人工确认、招呼语和发送选择修复 |
| 6 | [@atticus-zhou](https://github.com/atticus-zhou) | **6.5%** | AI 评分与招呼语重试、前台浏览器交互、送达验证和防重复发送 |
| 7 | [@fengziliang43-cmyk](https://github.com/fengziliang43-cmyk) | **6.4%** | 监测回复轮次、安全操作、本地凭据与面板交互；猎聘临时失败/保存失败保留断点的共同实现 |
| 8 | [@haohao-fly](https://github.com/haohao-fly) | **5.4%** | 岗位筛选、分页与统计；结构化评分、失败重试、投递队列和任务保护 |
| 9 | [@hdfhssg](https://github.com/hdfhssg) | **4.6%** | 学历与招聘类型筛选、评分上下文、岗位池排序、投递队列和额度提示 |
| 9 | [@meixiaoxie](https://github.com/meixiaoxie) | **4.6%** | 配置原子写入与无凭据下载；公司屏蔽、城市查询与 Windows 回归测试 |

[查看完整榜单、证据链接、历月快照与计算口径](CONTRIBUTORS.md)

## 许可证

本项目源码公开，采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。许可证允许符合其定义的非商业用途，以及为这些用途修改和分发本软件；商业使用不在该许可证的授权范围内，需事先取得另行书面授权。

因此，BossHunter 属于 **source-available（源码可用）的非商业许可软件**，不是 [OSI 定义下的开源软件](https://opensource.org/osd)。

## 参与项目

欢迎 [Star](https://github.com/shengjidaguai-china/BossHunter/stargazers)、提交 [Issue](https://github.com/shengjidaguai-china/BossHunter/issues) 或 Pull Request。大改动建议先开 Issue 讨论。

- 不接受绕过平台安全机制、规避检测或提高默认发送频率的 PR。
- 不接受绕过人工确认，或收集、上传、外发用户隐私数据的 PR。
- 所有修改必须走 PR 并通过 CI；贡献记录以合入主线的实际影响为准。

[查看贡献指南](CONTRIBUTING.md) · [查看完整贡献榜](CONTRIBUTORS.md) · [申请成为候选维护者](https://github.com/shengjidaguai-china/BossHunter/issues/new?template=maintainer_application.md) · [关注升级打怪开源社区](https://github.com/shengjidaguai-china)
