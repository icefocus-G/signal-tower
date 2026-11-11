# 信号塔 · Signal Tower

中文呈现的前沿 AI、时政、养生资讯聚合站。多源抓取 → 去重过滤 → 英文自动翻译 → 静态托管，每天自动重建，零服务器成本。

**没有缩水摘要，没有标题党绕弯，没有信息流广告。**

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

## 部署到 GitHub Pages（一劳永逸）

### 1. 新建仓库并推送

```bash
cd newsradar
git init
git add .
git commit -m "init: 信号塔"
git branch -M main
git remote add origin https://github.com/<你的用户名>/signal-tower.git
git push -u origin main
```

### 2. 开启 Actions 写权限

仓库 → **Settings → Actions → General → Workflow permissions** → 选 **Read and write permissions** → Save。

> 这一步不做，定时任务会因为没有推送权限而失败。

### 3. 开启 Pages

仓库 → **Settings → Pages** → Source 选 **Deploy from a branch** → Branch 选 **main**、目录选 **`/docs`** → Save。

大约 1 分钟后访问 `https://<你的用户名>.github.io/signal-tower/`。

### 4. 首次手动触发

仓库 → **Actions** → 左侧「每日构建」→ **Run workflow**。跑完 `docs/` 目录里就有数据了。

之后每天北京时间 **07:00 和 15:00** 自动重建（`.github/workflows/daily.yml` 里的 cron 可改）。

---

## 提升翻译质量（可选）

默认走免费翻译接口。GitHub Actions 跑在境外，会自动使用 Google 翻译端点，质量优于 MyMemory。

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
open http://127.0.0.1:8787

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
└── .github/workflows/daily.yml
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
- 免费翻译有速率限制，条目多时构建需要 1–2 分钟

---

## 许可

自用项目，随意取用。
