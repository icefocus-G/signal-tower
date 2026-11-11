# -*- coding: utf-8 -*-
"""
过滤层 —— 这个文件决定了"不缩水、不绕弯子"能不能成立。

四道闸门：
  1. 硬丢弃：广告软文、纯预告、无信息标题
  2. 相关性：AI 类目下，泛科技源的非 AI 内容降权
  3. 去重：URL 归一 + 标题指纹相似度
  4. 打分：来源权重 / 信息密度 / 时效，低分出局
"""
import re
import time
import unicodedata
from hashlib import sha1
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from fetcher import strip_html

# ---------- 1. 硬丢弃规则 ----------

# 广告 / 导流 / 无正文
JUNK_PATTERNS = [
    r"限时(优惠|折扣|抢购|特价)",
    r"点击(购买|下单|领取|报名|查看全文)",
    r"(双11|双十一|618|黑五|年货节).{0,6}(大促|促销|攻略|清单)",
    r"优惠券|领券|返现|拼团|秒杀",
    r"报名(开启|通道|链接)|扫码(进群|报名|加入)",
    r"(招聘|诚聘|招募).{0,8}(工程师|分析师|实习生|伙伴)",
    r"免责声明|版权声明|转载请注明",
    r"^(广告|推广|赞助内容|AD)[｜|:：]",
    r"(抽奖|福利|送礼).{0,10}(关注|转发|评论)",
    r"直播(预告|回放|预约)[｜|:：]?$",
    r"一文(带你看完|速览)全部(公告|政策)$",
    r"^(快讯|速报)[｜|:：]\s*$",
    r"^\s*$",
]

# 标题里出现、但基本等于"没内容"的信号
EMPTY_TITLE_PATTERNS = [
    r"^(最新|今日|重磅|突发|刚刚)[！!，,。：:]*$",
    r"^.{0,4}(盘点|汇总|合集)$",
    r"^(图片|视频|图集)(新闻)?$",
    # 人事简历、名单、纯视频栏目——信息量低且时效性差
    r"同志简历|个人简历|简历$",
    r"(领导|委员|理事|代表|执委).{0,24}(名单|名录)(公布|发布|出炉)?$",
    r"^(微视频|视频|图集|海报|H5|长图)[｜|:：]",
    r"^(新闻|财经|科技|AI|汽车)?早报[｜|:：]?$",
    r"^\d+月\d+日(新闻)?早报$",
    r"开盘$|收盘$|午评$|盘前$",
    r"避坑|薅羊毛|省钱攻略",
    # 股市盘面/基金行情：不是新闻，是行情播报
    r"\(\d{6}\)|（\d{6}）",                      # 基金/股票代码，如 512930
    r"(ETF|etf).{0,20}(涨|跌|成交|净流入|份额)",
    r"(标的指数|概念股|主力资金|融资余额|龙虎榜|北向资金)",
    r"(涨超|跌超|涨幅|跌幅|涨停|跌停|高开|低开|翻红|翻绿|收涨|收跌)\s*\d",
    r"(板块|概念).{0,10}(爆发|走强|走弱|领涨|领跌|异动)",
    r"^(沪指|深成指|创业板指|恒指|纳指|道指)",
]

# 聚合型内容（早报/日报/周报）——不是单条新闻，降权而非删除
DIGEST_RE = re.compile(
    r"(早报|晚报|日报|周报|月报|速递|速览|集锦|盘点|一周要闻|要闻速览|"
    r"daily\s*(brief|digest)|the\s+download|weekly|roundup|newsletter)",
    re.I,
)

# 时政类目下的"非时政"内容：养生、情感、娱乐、祝福
LIFE_PATTERNS = [
    r"洗澡|睡眠|失眠|减肥|养生|吃什么|食疗|锻炼|体检|长寿|免疫力",
    r"祝你|致敬|点赞|暖心|感人|泪目|太好哭|刷屏了",
    r"星座|运势|风水|属相",
    r"(明星|女星|男星|网红).{0,6}(恋情|分手|结婚|离婚|生子)",
    r"(电影|电视剧|综艺).{0,4}(票房|豆瓣|收视|开分)",
]
LIFE_RE = [re.compile(p, re.I) for p in LIFE_PATTERNS]

# 时政相关性：界面这类综合媒体，只有命中这些词才算时政
POLITICS_TERMS = [
    "国务院", "中央", "人大", "政协", "两会", "政策", "文件", "通知", "办法",
    "条例", "立法", "法案", "监管", "部委", "外交部", "国防部", "商务部",
    "发改委", "财政部", "央行", "证监会", "书记", "市长", "省长", "部长",
    "主席", "总理", "国务卿", "总统", "议会", "选举", "弹劾", "峰会", "会谈",
    "外交", "制裁", "关税", "军演", "停火", "冲突", "局势", "协议", "条约",
    "美联储", "加息", "降息", "通胀", "GDP", "就业", "失业率", "经济数据",
    "省委", "市委", "党委", "全会", "政治局", "反腐", "纪委", "检察",
]
POLITICS_RE = re.compile("|".join(re.escape(t) for t in POLITICS_TERMS), re.I)

JUNK_RE = [re.compile(p, re.I) for p in JUNK_PATTERNS]
EMPTY_RE = [re.compile(p, re.I) for p in EMPTY_TITLE_PATTERNS]

# ---------- 2. AI 相关性 ----------

AI_TERMS = [
    "ai", "a.i.", "人工智能", "大模型", "大语言模型", "llm", "gpt", "chatgpt", "openai",
    "claude", "anthropic", "gemini", "deepmind", "deepseek", "qwen", "通义", "文心",
    "豆包", "kimi", "月之暗面", "智谱", "glm", "llama", "mistral", "grok", "xai",
    "具身智能", "机器人", "自动驾驶", "agi", "多模态", "扩散模型", "transformer",
    "推理模型", "神经网络", "深度学习", "机器学习", "微调", "rag", "智能体", "agent",
    "prompt", "token", "算力", "英伟达", "nvidia", "h100", "b200", "gpu", "tpu",
    "模型训练", "模型发布", "开源模型", "对齐", "幻觉", "上下文窗口", "copilot",
    "sora", "midjourney", "stable diffusion", "语音合成", "ai 编程", "ai编程",
]

AI_RE = re.compile("|".join(re.escape(t) for t in AI_TERMS), re.I)

# 这些源主题本身就是 AI，不需要相关性加分/扣分
AI_NATIVE_SOURCES = {"jiqizhixin", "qbitai", "openai", "ar5iv"}

# ---------- 3. URL 归一化 ----------

TRACKING_PARAMS = re.compile(
    r"^(utm_|spm|from|share|ref|src|fbclid|gclid|_ga|scene|clicktime|suid|utm)$", re.I
)


def normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
    except ValueError:
        return url
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
         if not TRACKING_PARAMS.match(k)]
    path = p.path.rstrip("/")
    netloc = p.netloc.lower().replace("www.", "", 1)
    return urlunparse((p.scheme or "http", netloc, path, "", urlencode(q), ""))


def item_id(url: str) -> str:
    return sha1(normalize_url(url).encode("utf-8")).hexdigest()[:16]


# ---------- 4. 标题指纹 ----------

_PUNCT_RE = re.compile(r"[\s\u3000!-/:-@\[-`{-~，。！？、；：""''（）《》【】—…·|]+")


def fingerprint(title: str) -> set:
    t = _PUNCT_RE.sub("", title or "").lower()
    if len(t) < 4:
        return {t}
    return {t[i : i + 3] for i in range(len(t) - 2)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


# ---------- 5. 打分 ----------

def _cjk_len(s: str) -> int:
    return sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")


def freshness_score(ts, now=None) -> float:
    if not ts:
        return 6.0
    now = now or time.time()
    age_h = max(0.0, (now - ts) / 3600.0)
    if age_h <= 3:
        return 20.0
    if age_h <= 12:
        return 17.0
    if age_h <= 24:
        return 13.0
    if age_h <= 48:
        return 8.0
    if age_h <= 96:
        return 3.0
    return 0.0


def title_quality(title: str) -> float:
    n = len(title)
    if n < 6:
        return -30.0
    if n < 10:
        return 2.0
    if n <= 46:
        return 12.0
    if n <= 70:
        return 7.0
    return 2.0


def summary_quality(summary: str) -> float:
    n = len(summary or "")
    if n < 20:
        return -6.0
    if n < 60:
        return 4.0
    if n < 400:
        return 12.0
    if n < 1200:
        return 15.0
    return 11.0


def ai_relevance(title: str, summary: str, source_id: str) -> float:
    if source_id in AI_NATIVE_SOURCES:
        return 10.0
    blob = f"{title} {summary[:600]}"
    hits = len(set(m.group(0).lower() for m in AI_RE.finditer(blob)))
    if hits == 0:
        return -28.0     # 泛科技源里的非 AI 内容，直接压低
    if hits == 1:
        return 4.0
    if hits <= 3:
        return 14.0
    return 22.0


def is_junk(title: str, summary: str, category: str = "") -> tuple:
    """返回 (是否垃圾, 原因)。"""
    for rx in JUNK_RE:
        if rx.search(title):
            return True, f"广告/导流"
    for rx in EMPTY_RE:
        if rx.search(title):
            return True, "无信息标题"
    if _cjk_len(title) < 4 and len(re.findall(r"[a-zA-Z]", title)) < 12:
        return True, "标题过短"
    # 标题全大写 + 感叹号堆叠（典型标题党/站点导航）
    if title.count("！") + title.count("!") >= 3:
        return True, "标题党"
    # 时政频道里的养生/情感/娱乐内容——不属于时政
    if category == "politics":
        blob = f"{title} {summary[:80]}"
        for rx in LIFE_RE:
            if rx.search(blob):
                return True, "非时政内容"
    return False, ""


def route_category(item: dict) -> str:
    """
    双栖源（如界面新闻同时覆盖 AI 与政策）按内容路由。
    AI 术语命中 → ai；时政词命中 → politics；都不是 → other（丢弃）。
    """
    if item["category"] != "auto":
        return item["category"]
    blob = f"{item.get('raw_title','')} {item.get('raw_summary','')[:400]}"
    if AI_RE.search(blob):
        return "ai"
    if POLITICS_RE.search(blob):
        return "politics"
    return "other"


# ---------- 6. 主流程 ----------

def process(raw_items: list, max_age_hours: int = 120, now=None) -> tuple:
    """
    输入原始条目 → 输出 (干净的条目列表, 统计字典)
    """
    now = now or time.time()
    stats = {"input": len(raw_items), "junk": 0, "stale": 0, "duplicate": 0, "kept": 0}
    reasons = {}

    def bump(k):
        reasons[k] = reasons.get(k, 0) + 1

    seen_urls = {}
    candidates = []

    for it in raw_items:
        title = (it.get("raw_title") or "").strip()
        summary = (it.get("raw_summary") or "").strip()
        it["category"] = route_category(it)
        if it["category"] == "other":
            stats["junk"] += 1
            bump("与主题无关")
            continue

        bad, why = is_junk(title, summary, it["category"])
        if bad:
            stats["junk"] += 1
            bump(why[:16])
            continue

        ts = it.get("published")
        if ts and (now - ts) > max_age_hours * 3600:
            stats["stale"] += 1
            bump("过期")
            continue
        if ts and (ts - now) > 86400:      # 时间穿越，源本身有 bug
            ts = None

        url_key = normalize_url(it["url"])
        if url_key in seen_urls:
            stats["duplicate"] += 1
            bump("同链接")
            continue
        seen_urls[url_key] = True

        clean_summary = strip_html(summary)
        # RSS 摘要常在末尾重复标题
        if clean_summary.startswith(title):
            clean_summary = clean_summary[len(title):].lstrip(" -—:|：")
        # arXiv 摘要前缀
        clean_summary = re.sub(r"^(Abstract|摘要)\s*[:：]\s*", "", clean_summary)

        score = (
            it["weight"] * 50
            + title_quality(title)
            + summary_quality(clean_summary)
            + freshness_score(ts, now)
            + (ai_relevance(title, clean_summary, it["source_id"])
               if it["category"] == "ai" else 8.0)
        )
        # 聚合型早报/周报：不是单条新闻，降权放后排
        if DIGEST_RE.search(title):
            score -= 22

        item = dict(it)
        item.update(
            {
                "id": item_id(it["url"]),
                "title": title,
                "summary": clean_summary[:700],
                "summary_len": len(clean_summary),
                "published": ts,
                "score": round(score, 1),
                "_fp": fingerprint(title),
            }
        )
        candidates.append(item)

    # ---- 标题近重复合并：保留分数高的 ----
    # 稳定排序：同分同时间时按 id 兜底，避免并发抓取的完成顺序影响结果
    candidates.sort(key=lambda x: (-x["score"], -(x["published"] or 0), x["id"]))
    kept = []
    for c in candidates:
        dup = False
        for k in kept:
            if c["category"] != k["category"]:
                continue
            if jaccard(c["_fp"], k["_fp"]) >= 0.72:
                dup = True
                break
        if dup:
            stats["duplicate"] += 1
            bump("标题雷同")
            continue
        kept.append(c)

    # ---- 质量阈值 ----
    # 每天只给一份能看完的量：门槛抬高，宁可少几条，不要塞满
    threshold = 66.0
    final = [k for k in kept if k["score"] >= threshold]

    # ---- 源多样性重排：避免单一媒体（如界面）刷屏 ----
    final = diversify(final, penalty=1.4)

    stats["kept"] = len(final)
    stats["dropped_lowscore"] = len(kept) - len(final)
    stats["reasons"] = dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:8])

    for k in final:
        k.pop("_fp", None)
        k.pop("raw_summary", None)
        k.pop("raw_title", None)
    return final, stats


def diversify(items: list, penalty: float = 1.4) -> list:
    """
    贪心重排：同源每多出现一次，后续候选扣 penalty 分。
    既保留"重要的在前"，又避免单一媒体霸屏。
    """
    remaining = list(items)
    out, counts = [], {}
    while remaining:
        best, best_val = None, float("-inf")
        for it in remaining:
            val = it["score"] - penalty * counts.get(it["source_id"], 0)
            if val > best_val:
                best, best_val = it, val
        out.append(best)
        remaining.remove(best)
        counts[best["source_id"]] = counts.get(best["source_id"], 0) + 1
    return out


def extract_tags(item: dict) -> list:
    """从标题+摘要里抽 2-3 个标签，供前端展示。"""
    blob = f"{item['title']} {item.get('summary','')[:300]}".lower()
    buckets = [
        ("大模型", ["大模型", "llm", "gpt", "claude", "gemini", "deepseek", "qwen", "模型发布"]),
        ("芯片算力", ["芯片", "算力", "英伟达", "nvidia", "gpu", "h100", "b200", "tsmc", "台积电"]),
        ("智能体", ["智能体", "agent", "copilot", "mcp"]),
        ("具身智能", ["机器人", "具身", "robot", "自动驾驶"]),
        ("多模态", ["多模态", "sora", "视频生成", "图像生成", "语音"]),
        ("政策监管", ["监管", "政策", "法案", "合规", "备案", "立法"]),
        ("融资并购", ["融资", "估值", "收购", "ipo", "独角兽"]),
        ("开源", ["开源", "open source", "权重"]),
        ("经济", ["经济", "gdp", "消费", "就业", "物价", "cpi", "贸易"]),
        ("外交", ["外交", "会谈", "访问", "峰会", "联合国"]),
        ("民生", ["民生", "教育", "医疗", "养老", "住房"]),
    ]
    tags = [name for name, kws in buckets if any(k in blob for k in kws)]
    return tags[:3]
