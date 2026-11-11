# 信号塔 · Signal Tower

中文呈现的前沿 AI、时政、养生资讯聚合站。多源抓取 → 去重过滤 → 英文自动翻译 → 静态托管，每天自动重建，零服务器成本。

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

## 部署状态（已完成）

| 项目 | 状态 |
|---|---|
| 仓库 | `icefocus-G/signal-tower`（public） |
| 站点 | https://icefocus-g.github.io/signal-tower/ |
| Pages | main 分支 `/docs` 目录，已启用 |
| Actions 写权限 | 已设为 Read and write |
| 首次构建 | 通过，21/21 源在线，574 条 → 保留 202 条 |
| 定时 | 每天北京时间 07:00、15:00（UTC 23:00、07:00） |

`push` 到 main 也会触发一次构建，所以改完代码推上去就能看到新数据。

### 换一台机器 / 重建站点时的步骤

```bash
git clone https://github.com/icefocus-G/signal-tower.git
cd signal-tower
python3 build.py --out docs --articles 20   # 本地验证
git add -A && git commit -m "update" && git push
```

推上去后 Actions 会自动重建并回写 `docs/`，Pages 自动更新。

> 定时任务与手动触发可能同时跑，`daily.yml` 的提交步骤已带 rebase 重试；`docs/` 是构建产物，冲突时保留本次构建结果。

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
