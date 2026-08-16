# 大V动态监控推送智能体（v1 免费版）

自动监控你关注的**雪球**和**微博**大V的**全部动态（发帖 / 转发 / 评论 / 文章）**，新动态在 **5~15 分钟内**推送到你的**微信**（企业微信应用消息），并提供简洁的本地网页用于查看动态、增删大V。

- **零依赖**：只用 Python 标准库实现，无需 pip install 任何第三方包（只需安装 Python 3.10+）
- **双保险**：本地小工具（电脑开机时用，手动刷新即时）+ GitHub Actions 公开仓库（24 小时自动兜底，每 5 分钟一次，免费不限时长）
- **易扩展**：在网页「管理」里点几下即可增删大V，无需改代码

---

## 目录结构

```
v-monitor/
├── run_local.py                # 本地工具启动器（网页 + 可选持续轮询）
├── config.json                 # 配置：轮询间隔、企业微信、大V列表
├── .env.local                  # 密钥（Cookie、企业微信），已被 git 忽略
├── core/                       # 核心：抓取、去重、推送、存储、Git
│   ├── collectors/             #   雪球 / 微博 采集器
│   ├── pipeline.py             #   主流程：抓取→推送→存储
│   ├── notifier.py             #   企业微信推送（预留其他渠道）
│   └── ...
├── web/                        # 本地网页（标准库 http.server，无框架）
├── scripts/
│   ├── refresh_cookies.py      # 获取/刷新 雪球·微博 Cookie
│   ├── resolve_influencers.py  # 解析大V的数字 ID（首次必跑）
│   └── run_once.py             # 命令行跑一次（Actions 也用它）
├── .github/workflows/monitor.yml  # GitHub Actions 定时监控
└── data/                       # 运行数据（state.json、items.jsonl、日志）
```

---

## 快速开始（约 30~40 分钟，一次性配置）

### 第 1 步：安装 Python
到 [python.org](https://www.python.org/downloads/) 下载并安装 **Python 3.10 或更高版本**（Windows 安装时勾选 *Add python.exe to PATH*）。

### 第 2 步：拿到代码并建 GitHub 公开仓库
1. 本目录已是 git 仓库。在 [github.com](https://github.com) 新建一个 **Public** 公开仓库，名字如 `v-monitor`（公开仓库的 Actions 免费不限时长）。
2. 在本目录执行：
   ```
   git remote add origin https://github.com/<你的用户名>/v-monitor.git
   git branch -M main
   git push -u origin main
   ```
   > 若不想公开，可建私有仓库，但免费分钟数只够约 60 分钟轮询一次（实时性差），建议按方案用公开仓库。

### 第 3 步：注册企业微信并绑定个人微信（约 20 分钟）
1. 打开 [企业微信官网](https://work.weixin.qq.com) 注册（免费，个人可注册）。
2. 进入管理后台：
   - **我的企业 → 企业信息**：复制「企业ID」→ 即 `WECOM_CORPID`
   - **应用管理 → 应用 → 自建**：创建一个自建应用，记下「Secret」（`WECOM_SECRET`）和「AgentId」（`WECOM_AGENT_ID`）
3. 绑定个人微信：**我的企业 → 微信插件**，用个人微信扫码绑定；之后企业微信应用消息会直接出现在个人微信里。
4. 确认你的账号名（默认推送给所有人 `@all`；也可在 config.json 的 `wecom.touser` 指定成员账号）。

### 第 4 步：获取雪球 / 微博 Cookie
运行：
```
python scripts/refresh_cookies.py
```
按提示操作：
1. 浏览器打开并登录雪球 / 微博
2. 按 F12 → Network → 刷新页面 → 右键任意请求 → **Copy as cURL (bash)**
3. 粘贴到终端，脚本会自动提取 Cookie 并保存到 `.env.local`（不会被提交）
4. 脚本会测试 Cookie 是否有效，并提示是否用 `gh` 上传到 GitHub Secrets（也可手动配置）

> Cookie 会过期（通常 1~4 周）。过期时你会收到微信提醒，重新运行本脚本即可。

### 第 5 步：解析 12 位大V的 ID（首次必跑）
运行：
```
python scripts/resolve_influencers.py
```
- 雪球：自动搜索匹配；匹配不到时粘贴主页链接（`xueqiu.com/u/123456`）
- 微博：列出同名账号，**请人工确认选择**（同名很多，选错会监控错人）

之后也可随时在网页「管理」里增删大V（粘贴主页链接或数字 ID 即可）。

### 第 6 步：配置 GitHub Actions Secrets 并启动
1. 仓库 → **Settings → Secrets and variables → Actions**，添加：
   - `WECOM_CORPID`、`WECOM_SECRET`、`WECOM_AGENT_ID`（`WECOM_TOUSER` 可选）
   - `XUEQIU_COOKIE`、`WEIBO_COOKIE`
2. 推送代码后，Actions 的 `大V动态监控` 工作流会每 5 分钟自动运行（也可在 Actions 页手动 Run workflow 测试）。
3. 本机启动网页工具：
   ```
   python run_local.py
   ```
   浏览器会自动打开 http://127.0.0.1:8787 —— 手机与电脑都能用（手机需开启「设置 → 允许局域网访问」并重启，用 `http://电脑IP:8787` 访问）。

---

## 网页功能

| 页面 | 功能 |
| --- | --- |
| 动态 | 按平台筛选、搜索作者/内容、查看发帖/转发/评论卡片、一键「立即刷新」 |
| 管理 | 增删大V、停用/启用；增删后自动同步到 GitHub |
| 设置 | 推送/密钥状态、轮询间隔、最近运行结果、日志、允许局域网访问、发送测试消息 |

---

## 常见问题

**收不到微信推送？**
依次检查：设置页各密钥是否「已配置」→ 点击「发送测试消息」→ 查看日志页的错误信息；企业微信需确认个人微信已绑定（第 3 步）。

**微博返回 432 / 频繁限制？**
说明请求太密。本项目微博默认每 10 分钟轮询一次（config.json 里 `poll_interval_minutes.weibo`），一般不会触发；若仍触发，把间隔调大（如 15）即可。评论区接口若被风控，会自动降级为「仅发帖/转发」并在界面标注。

**提示 Cookie 失效？**
运行 `python scripts/refresh_cookies.py` 重新获取并上传 Secrets。

**「允许局域网访问」怎么用？**
在设置页打开开关并保存，重启 `run_local.py` 后生效；建议同时设置访问口令。手机浏览器输入 `http://电脑局域网IP:8787`。

**数据会公开吗？**
公开仓库里会包含抓取到的大V动态（大V发布的内容本身是公开的）和监控状态。密钥（Cookie、企业微信 Secret）全部放在 Secrets，不会进仓库。若介意公开，可改用私有仓库（推送间隔会变长）或升级云服务器。

---

## 技术说明

- 纯 Python 标准库（`urllib`、`http.server`），无任何第三方依赖，安装即用、Actions 运行快。
- 雪球接口：`/v4/statuses/user_timeline.json`（发帖/转发/文章）+ 候选评论端点（见 `core/collectors/xueqiu.py` 的 `COMMENTS_ENDPOINT`，如不可用自动降级）。
- 微博接口：`m.weibo.cn/api/container/getIndex`（发帖/转发）+ `weibo.com/ajax/profile/getComments`（该用户评论，受风控时降级）。
- 去重与增量：`data/state.json` 记录每个用户的已见条目；首次运行只回填最近 6 小时（`initial_backfill_hours`）。
- 历史存储：`data/items.jsonl`，每个平台保留最近 2000 条，自动裁剪。

## 后续升级路径

- 将服务部署到云服务器（约 30~60 元/月）或家里 NAS：轮询可缩短到 1~2 分钟、网页可公网访问（加口令）。
- 需要时可在 `core/notifier.py` 增加 PushPlus / Server酱 / 钉钉 渠道。
- 需要时增加 AI 总结（接入大模型 API 自动提炼长文要点）。
