# -*- coding: utf-8 -*-
"""
信号塔 · 源配置
================
每一条源都经过真实请求验证（返回的是 RSS/Atom，而不是反爬 HTML）。
weight 决定质量分权重（0-1）。

注：机器之心 / 36氪 / 量子位 / 观察者网的公开 RSS 已废弃或返回反爬页面，
    这些站点的内容通过其他渠道（InfoQ、界面、钛媒体）间接覆盖。
"""

SOURCES = [
    # ================= AI 前沿 · 中文原生 =================
    {
        "id": "infoq",
        "name": "InfoQ 中文",
        "url": "https://www.infoq.cn/feed",
        "category": "ai",
        "lang": "zh",
        "weight": 0.9,
        "max": 40,
        "desc": "技术架构与工程实践，AI 落地细节最扎实",
    },
    {
        "id": "jiemian",
        "name": "界面新闻",
        "url": "https://a.jiemian.com/index.php?m=article&a=rss",
        "category": "auto",
        "lang": "zh",
        "weight": 0.85,
        "max": 60,
        "desc": "商业与资本视角，按内容自动分流到 AI / 时政",
    },
    {
        "id": "tmtpost",
        "name": "钛媒体",
        "url": "https://www.tmtpost.com/rss",
        "category": "ai",
        "lang": "zh",
        "weight": 0.75,
        "max": 40,
        "desc": "产业观察，观点鲜明",
    },
    {
        "id": "geekpark",
        "name": "极客公园",
        "url": "https://www.geekpark.net/rss",
        "category": "ai",
        "lang": "zh",
        "weight": 0.75,
        "max": 30,
        "desc": "产品与行业深度",
    },
    {
        "id": "solidot",
        "name": "Solidot",
        "url": "https://www.solidot.org/index.rss",
        "category": "ai",
        "lang": "zh",
        "weight": 0.8,
        "max": 25,
        "desc": "极客圈二手精选，信息密度高",
    },
    {
        "id": "ithome",
        "name": "IT之家",
        "url": "https://www.ithome.com/rss/",
        "category": "ai",
        "lang": "zh",
        "weight": 0.6,
        "max": 60,
        "desc": "快讯量大，靠后续过滤提纯",
    },
    {
        "id": "oschina",
        "name": "开源中国",
        "url": "https://www.oschina.net/news/rss",
        "category": "ai",
        "lang": "zh",
        "weight": 0.65,
        "max": 30,
        "desc": "开源模型与开发者生态",
    },
    {
        "id": "sspai",
        "name": "少数派",
        "url": "https://sspai.com/feed",
        "category": "ai",
        "lang": "zh",
        "weight": 0.55,
        "max": 15,
        "desc": "工具与效率视角",
    },
    # ================= AI 前沿 · 英文源（自动翻译） =================
    {
        "id": "openai",
        "name": "OpenAI 官方",
        "url": "https://openai.com/news/rss.xml",
        "category": "ai",
        "lang": "en",
        "weight": 0.95,
        "max": 12,
        "desc": "一手发布，未经转述",
    },
    {
        "id": "mittr",
        "name": "MIT 科技评论",
        "url": "https://www.technologyreview.com/feed/",
        "category": "ai",
        "lang": "en",
        "weight": 0.9,
        "max": 25,
        "desc": "学术与产业交叉的深报道",
    },
    {
        "id": "hn",
        "name": "Hacker News",
        "url": "https://hnrss.org/frontpage",
        "category": "ai",
        "lang": "en",
        "weight": 0.85,
        "max": 40,
        "desc": "全球技术圈当日风向标",
    },
    {
        "id": "techcrunch",
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "category": "ai",
        "lang": "en",
        "weight": 0.8,
        "max": 40,
        "desc": "硅谷一手融资与产品动态",
    },
    {
        "id": "verge",
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "category": "ai",
        "lang": "en",
        "weight": 0.75,
        "max": 30,
        "desc": "消费科技与平台生态",
    },
    {
        "id": "arxiv_ai",
        "name": "arXiv cs.AI",
        "url": (
            "https://export.arxiv.org/api/query?"
            "search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=25"
        ),
        "category": "ai",
        "lang": "en",
        "weight": 0.6,
        "max": 25,
        "desc": "论文摘要，前沿但噪声大",
    },
    # ================= 时政 · 中文 =================
    {
        "id": "xinhua_pol",
        "name": "新华网 · 时政",
        "url": "http://www.news.cn/politics/news_politics.xml",
        "category": "politics",
        "lang": "zh",
        "weight": 0.95,
        "max": 60,
        "desc": "权威发布，政策原文优先级最高",
    },
    {
        "id": "people_pol",
        "name": "人民网 · 时政",
        "url": "http://www.people.com.cn/rss/politics.xml",
        "category": "politics",
        "lang": "zh",
        "weight": 0.9,
        "max": 60,
        "desc": "与新华网互补的官方视角",
    },
    {
        "id": "chinanews",
        "name": "中新网 · 国内",
        "url": "https://www.chinanews.com.cn/rss/china.xml",
        "category": "politics",
        "lang": "zh",
        "weight": 0.8,
        "max": 40,
        "desc": "国内时政与社会民生",
    },
    {
        "id": "chinanews_world",
        "name": "中新网 · 国际",
        "url": "https://www.chinanews.com.cn/rss/world.xml",
        "category": "politics",
        "lang": "zh",
        "weight": 0.8,
        "max": 40,
        "desc": "国际局势，中文视角",
    },
    {
        "id": "chinanews_finance",
        "name": "中新网 · 财经",
        "url": "https://www.chinanews.com.cn/rss/finance.xml",
        "category": "politics",
        "lang": "zh",
        "weight": 0.75,
        "max": 35,
        "desc": "宏观与政策落地的经济面",
    },
    {
        "id": "chinanews_scroll",
        "name": "中新网 · 滚动",
        "url": "https://www.chinanews.com.cn/rss/scroll-news.xml",
        "category": "politics",
        "lang": "zh",
        "weight": 0.7,
        "max": 40,
        "desc": "突发与快讯",
    },
    # ================= 养生 · 健康（按主题过滤） =================
    {
        "id": "chinanews_health",
        "name": "中新网 · 健康",
        "url": "https://www.chinanews.com.cn/rss/health.xml",
        "category": "health",
        "lang": "zh",
        "weight": 0.8,
        "max": 40,
        "desc": "健康频道，仅保留与四个代谢主题相关的内容",
    },
]


def by_id(sid):
    for s in SOURCES:
        if s["id"] == sid:
            return s
    return None


def all_ids():
    return [s["id"] for s in SOURCES]
