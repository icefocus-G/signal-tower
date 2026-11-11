# 信号塔 · Signal Tower

中文呈现的前沿 AI、时政、养生资讯聚合站。多源抓取 → 去重过滤 → 英文自动翻译 → 本地单文件，双击图标 10 秒出当天简报，零服务器成本。

**没有缩水摘要，没有标题党绕弯，没有信息流广告。**

**线上地址：https://icefocus-g.github.io/signal-tower/**
**仓库：https://github.com/icefocus-G/signal-tower**

---

## 三个栏目

| 栏目 | 内容 | 来源 |
|---|---|---|
| **前沿 AI** | 模型发布、产业动态、学术前沿 | InfoQ、界面、钛媒体、极客公园、Solidot、IT之家、开源中国、Hacker News、TechCrunch、MIT 科技评论、OpenAI、arXiv、The Verge |
| **时政** | 政策发布、国际局势、宏观经济 | 新华网时政、人民网时政、中新网（国内/国际/财经/滚动）、界面新闻 |
| **养生** | 胆囊术后、高血脂、高尿酸、胰腺脂肪浸润 | 指南要点（本地知识）+ 中新网健康 + Europe PMC 循证文献 |

养生栏目不像前两个栏目那样追求"最新"，而是围绕四个主题维护一份可长期参考的要点集：饮食、生活方式、复查信号、常见误区，每条都标注依据来源。文献部分只取综述与指南类型，不取个案报道。

---

## 它怎么工作

```
抓取 21 个 RSS/API 源
        ↓
四道过滤闸门
  ① 硬丢弃：广告、导流、"一文读懂"、简历名单、纯视频
  ② 相关性：泛科技源里与 AI 无关的内容降权出局
  ③ 去重：URL 归一化 + 标题 3-gram Jaccard ≥ 0.72 合并
  ④ 打分：来源权重 + 信息密度 + 时效，低于 62 分淘汰
        ↓
源多样性重排（同源每多一条扣 1.4 分，防止单一媒体霸屏）
        ↓
英文翻译（三级降级：LLM → Google → MyMemory）
        ↓
静态文件 → GitHub Pages
```

### 关于过滤

实测数据：一次抓取约 **550 条原始条目**，最终保留约 **200 条**。被淘汰的包括过期旧闻、同链接重复、标题雷同、养生软文、商业导购、人事简历名单。

判断"无效"的规则都写在 `filtering.py` 里，你可以随时加自己的规则——比如不想看某类标题党，往 `JUNK_PATTERNS` 加一条正则即可。

---

## 它是一份每日简报，不是实时快讯

定位很明确：**每天一份整理好的三栏简报，条数控制在能看完的量，感兴趣的条目点进去看原文。**

- **每天 07:00 自动生成**：`launchd` 定时任务在后台跑一次，不弹窗、不打扰。电脑关机或休眠错过的时间点，唤醒后系统会补跑。
- **点图标秒开**：`docs/offline.html` 如果是今天生成的，双击图标直接打开，不再重新抓取。只有「今天还没生成」才现场抓，那时会弹一个带进度条的窗口。
- **云端**：Actions 的定时与 push 触发**已全部取消**，GitHub 那边不自动跑，只在你想更新网页版时手动点一次 `Run workflow`。

状态栏显示「数据 X 小时前」，一眼就知道这份简报是不是今天的。

### 每天看多少条

`config.json` 的 `max_items_per_category` 现在是 **25**（早前是 90），`filtering.py` 的质量阈值从 62 提到 **66**。实测一次抓 549 条原始条目，最终留 **72 条**（AI 25 / 时政 25 / 养生 22），页面 157 KB——十屏之内能扫完。

嫌多就把 `max_items_per_category` 调到 15；觉得漏了重要消息就回调到 35，同时把 `threshold` 降回 62。

### 关于"实时"

试过，但这条路在境内不成立：浏览器直接抓 RSS 需要 CORS 放行，实测 `allorigins`、`codetabs`、`corsproxy`、`cors.lol` 全部不可用（000 / 401 / 429），中文源自身也不发 CORS 头。要秒级实时只能自建服务器或 Worker——为一份每日简报不值得。

---

## 双击图标，看今天的简报

桌面的 **`信号塔`**（指向 `~/Applications/信号塔.app`）有两种行为：

| 情况 | 表现 |
|---|---|
| 今天已经生成过 | **直接打开页面，秒出**，弹一条「今天 HH:MM 的简报已就绪」 |
| 今天还没生成 | 弹进度窗，四条进度（抓取 → 过滤 → 翻译 → 生成），走完自动打开 |

进度窗是本机 `tools/progress_ui.py`（tkinter，系统自带，零依赖）。它只负责"看得见"：真正的活是 `build.py` 在干，这里读它的 stdout，按 `[n/4]` 标记推进度条，最后报条数。

`刷新.command` 是终端版入口，效果相同但会开个终端窗口显示完整日志，适合排查问题。

### 每日定时任务

```bash
./安装定时任务.command        # 装（只需一次）
launchctl list | grep signaltower   # 看是否在跑
launchctl bootout gui/$(id -u)/local.signaltower.daily   # 卸
```

生成的是 `~/Library/LaunchAgents/local.signaltower.daily.plist`，每天 07:00 调一次 `refresh.sh`（`ST_NO_OPEN=1`，不弹浏览器），日志写 `build/launchd.log`。

`refresh.sh` 开头会自动检查：「plist 不存在、`launchctl list` 里也没这个任务」就顺手装一次，装失败不阻塞本次生成。所以正常情况下双击一次图标，定时任务就装好了，不用单独跑安装脚本。

**装不上怎么办**：`launchctl` 必须在真实的图形登录会话里才能操作 `gui/$UID` 域，被隔离的环境（比如自动化工具的子进程）会报 `Bootstrap failed: 5: Input/output error`。在终端里手动跑一次 `./安装定时任务.command` 就能成功。

### 重建启动器

图标和 `.app` 都是脚本生成的，换机器或改了图标设计后重跑一次即可：

```bash
python3 tools/make_app.py
```

产物：`~/Applications/信号塔.app`、桌面链接、项目里的 `刷新.command`、`build/icon.icns`。图标是纯 Python 画的——手写 PNG + `iconutil`，不依赖任何图形库。

**为什么用 `osacompile` 而不是自己拼 bundle**：`.app` 的主可执行文件必须是 Mach-O 二进制。早前版本把 bash 脚本直接写成 `CFBundleExecutable`，命令行跑得好好的，Finder 双击却起不来——LaunchServices 拿到的不是可执行映像，`spctl` 也判 rejected。`osacompile` 生成的 applet 是系统编译的通用二进制，图标和名字另外贴上去就行。

**为什么桌面只放链接**：`~/Desktop` 在 iCloud 同步范围内（`com~apple~CloudDocs/Desktop`），同步会改写文件、破坏 `.app` 的签名。app 放在 `~/Applications`（本地、不同步），桌面只留一个 42 字节的符号链接。

### 只保留今天的

双击图标用的是 `--max-age-hours 48`，只留最近两天的条目。想要更严格的当天内容：

```bash
python3 build.py --out docs --articles 0 --translate title --max-age-hours 24
```

### 出问题看日志

App 版没有终端，输出写在 `build/refresh.log`（不能放 `docs/`，那边每次构建会被整个重建）。

---

## 部署状态（已完成）

| 项目 | 状态 |
|---|---|
| 仓库 | `icefocus-G/signal-tower`（public） |
| 站点 | https://icefocus-g.github.io/signal-tower/ |
| 单文件版 | https://icefocus-g.github.io/signal-tower/offline.html |
| Pages | **由 Actions 产物部署**（`build_type: workflow`），不再从分支目录读 |
| 定时 | **已取消**，云端不再自动生成 |
| 翻译缓存 | 用 `actions/cache` 跨次复用，冷启动翻译几百条，热缓存只翻新增 |

push 到 main **不再触发构建**，只有 Actions 页面的 `Run workflow` 会跑。数据不提交进 git，所以高频构建不会把仓库撑大。

### 文件放在哪

```
/Volumes/02-program/[0000]AI程序操作/AI-新闻/     ← 项目根（源码 + 产物 + 缓存）
~/Applications/信号塔.app                       ← 真正的应用（本地磁盘，不进 iCloud）
~/Desktop/信号塔.app -> 上面那个                 ← 桌面图标是个符号链接
```

改了项目位置或重画了图标，跑一次 `python3 tools/make_app.py`，app 与桌面链接会一起重建。

### 三档构建

```bash
python3 build.py --out docs --articles 20 --translate full   # 全量简报（云端每天用这个）
python3 build.py --out docs --articles 0  --translate title   # 快速版：只翻标题，约 1 分钟
python3 build.py --out docs --translate none                  # 只抓不译
```

加 `--skip-if-unchanged` 时，若条目与译文跟上一版完全一致就不重写、不发布（靠 `content_hash` 判断）。为了让指纹稳定，抓取结果会先按「来源 / 时间 / guid」排一次序，去重和同分排序只由内容决定，不受并发完成顺序影响。云端每日简报**不用**这个开关——简报本身要体现当天这次生成。

### 换一台机器 / 本地重建

```bash
git clone https://github.com/icefocus-G/signal-tower.git
cd signal-tower
python3 build.py --out docs --articles 20   # 本地验证
open docs/offline.html                      # 双击也能看
```

`docs/` 是构建产物，已加入 `.gitignore`，由 Actions 每次生成并部署。

---

## 提升翻译质量（可选）

默认走免费翻译接口。GitHub Actions 跑在境外，会自动使用 Google 翻译端点，质量优于 MyMemory。（实测 Actions 上仍走了 MyMemory，说明 Google 端点在运行环境里被探测为不可用，属正常降级。）

想让译文更准确，可以接自己的大模型：

**仓库 → Settings → Secrets and variables → Actions → New repository secret**

| Secret | 值 |
|---|---|
| `LLM_API_KEY` | 你的 API Key |
| `LLM_BASE_URL` | 如 `https://api.deepseek.com/v1`（OpenAI 兼容接口均可） |
| `LLM_MODEL` | 如 `deepseek-chat` |

没配也能用，只是译文会生硬一些。

---

## 本地运行

```bash
# 方式一：动态服务（带全文抓取、点开即翻）
python3 server.py
open http://127.0.0.1:8890

# 方式二：构建静态文件
python3 build.py --out dist --articles 20
cd dist && python3 -m http.server 8899
open http://127.0.0.1:8899

# 方式三：macOS 双击
./start.command
```

零第三方依赖，只需 Python 3.9+。

> 本地打开 HTML 文件（file://）会因为浏览器安全策略读不到 JSON，必须走上面的 HTTP 方式。

---

## 目录结构

```
newsradar/
├── sources.py        源清单（改这里增删来源）
├── fetcher.py        抓取、RSS/Atom 解析、正文抽取
├── filtering.py      四道过滤闸门 + 打分 + 去重 + 多样性重排
├── translate.py      三级翻译引擎 + 术语校正 + 缓存
├── health.py         养生栏目：主题定义、指南要点、Europe PMC
├── pipeline.py       聚合管线（本地服务与静态构建共用）
├── build.py          静态构建
├── server.py         本地动态服务
├── config.json       配置
├── static/index.html 前端（单文件，无框架）
├── docs/             GitHub Pages 产物（由构建生成，勿手改）
│   ├── index.html
│   ├── offline.html  单文件离线版，数据内联
│   └── data/*.json   各栏目数据
└── .github/
    ├── workflows/daily.yml  每日构建
    └── summary.py     构建摘要（Steps Summary）
```

---

## 加源的方法

编辑 `sources.py`，追加一条：

```python
{
    "id": "my_source",          # 唯一标识
    "name": "我的源",
    "url": "https://example.com/feed",
    "category": "ai",           # ai / politics / health / auto
    "lang": "zh",               # zh 不翻译，en 自动翻译
    "weight": 0.8,              # 0-1，影响排序权重
    "max": 30,                  # 单次最多取几条
    "desc": "一句话说明",
}
```

`category: "auto"` 用于综合媒体，会按内容自动分流到 AI 或时政，两边都不沾的直接丢弃。

**注意**：很多中文媒体的 RSS 已经停更或返回反爬页面。验证方法：

```bash
curl -sL "https://example.com/feed" | head -c 80
```

输出应该以 `<?xml` 或 `<rss` 开头。如果是 `<!DOCTYPE html>`，说明这个源已经废了。

---

## 已知限制

- 医学内容为公开指南整理，**不构成诊疗建议**，具体方案请咨询医生
- 中文健康类 RSS 生态基本消亡（丁香医生、果壳、健康时报均无可用订阅源），养生栏目以指南要点和英文文献为主
- 部分源有反爬（机器之心、36氪、量子位、观察者网已失效并从清单移除）
- The Verge 与 arXiv 在境内不通、在 GitHub Actions 可达——所以本地构建时这两个源会显示异常，线上是 21/21 全在线
- 免费翻译有速率限制，条目多时构建需要 2–7 分钟（实测 Actions 上 395 秒）

---

## 许可

自用项目，随意取用。
