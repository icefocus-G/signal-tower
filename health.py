# -*- coding: utf-8 -*-
"""
养生栏目 —— 四个代谢相关主题的定向聚合
========================================
设计原则：
  1. 不给"偏方"，只给公开指南层面的饮食、生活方式、监测建议；
  2. 所有要点标注依据来源，并明确"个体方案须由医生确定"；
  3. 资讯流只保留与主题相关的内容，泛健康新闻一律不进；
  4. 循证文献取自 Europe PMC，仅取综述/指南类，不取个案报道。

四个主题的共同点：都与代谢、胆汁酸/脂质代谢、胰酶分泌相关，
所以它们的饮食策略有大量重叠（限酒、控精制糖、控饱和脂肪、减重）。
"""
import json
import os
import time
import urllib.parse
import urllib.request

import fetcher

# ============================================================
# 主题定义
# ============================================================

TOPICS = [
    {
        "id": "gallstone",
        "name": "胆囊术后",
        "short": "胆囊切除后的消化适应",
        "keywords": [
            "胆囊", "胆结石", "胆石", "胆囊炎", "胆囊切除", "腹腔镜胆囊",
            "胆总管", "胆汁反流", "胆汁酸", "胆道",
        ],
        "epmc_query": (
            '(TITLE:"cholecystectomy" OR TITLE:"gallstone" OR TITLE:"postcholecystectomy") '
            'AND (TITLE:"diet" OR TITLE:"nutrition" OR TITLE:"bile acid" OR TITLE:"diarrhea") '
            'AND (PUB_TYPE:"Review" OR PUB_TYPE:"Guideline") AND LANG:"eng" AND (FIRST_PDATE:[2019-01-01 TO 2026-12-31])'
        ),
    },
    {
        "id": "lipid",
        "name": "高血脂",
        "short": "血脂管理与心血管风险",
        "keywords": [
            "血脂", "胆固醇", "甘油三酯", "低密度脂蛋白", "LDL", "高血脂",
            "动脉粥样", "他汀", "调脂", "斑块", "冠心病", "心梗",
        ],
        "epmc_query": (
            '(TITLE:"hyperlipidemia" OR TITLE:"hypercholesterolemia" OR TITLE:"dyslipidemia" '
            'OR TITLE:"triglyceride") AND (TITLE:"diet" OR TITLE:"nutrition" OR '
            'TITLE:"lifestyle" OR TITLE:"guideline") AND '
            '(PUB_TYPE:"Review" OR PUB_TYPE:"Guideline") AND LANG:"eng" AND (FIRST_PDATE:[2019-01-01 TO 2026-12-31])'
        ),
    },
    {
        "id": "uric",
        "name": "高尿酸",
        "short": "尿酸控制与痛风预防",
        "keywords": [
            "尿酸", "痛风", "高尿酸血症", "嘌呤", "别嘌醇", "非布司他",
            "尿酸结石", "关节红肿",
        ],
        "epmc_query": (
            '(TITLE:"hyperuricemia" OR TITLE:"gout" OR TITLE:"uric acid") AND '
            '(TITLE:"diet" OR TITLE:"nutrition" OR TITLE:"fructose" OR TITLE:"lifestyle") AND '
            '(PUB_TYPE:"Review" OR PUB_TYPE:"Guideline") AND LANG:"eng" AND (FIRST_PDATE:[2019-01-01 TO 2026-12-31])'
        ),
    },
    {
        "id": "pancreas",
        "name": "胰腺脂肪浸润",
        "short": "胰脂肪沉积与胰腺功能保护",
        "keywords": [
            "胰腺", "脂肪胰", "胰腺脂肪", "脂肪浸润", "胰酶", "胰腺炎",
            "胰腺外分泌", "胰管", "脂肪泻",
        ],
        "epmc_query": (
            '(TITLE:"pancreatic steatosis" OR TITLE:"fatty pancreas" OR '
            'TITLE:"pancreatic fat") AND (TITLE:"diet" OR TITLE:"weight loss" OR '
            'TITLE:"nutrition" OR TITLE:"exocrine") AND LANG:"eng" AND (FIRST_PDATE:[2019-01-01 TO 2026-12-31])'
        ),
    },
]

TOPIC_BY_ID = {t["id"]: t for t in TOPICS}


# ============================================================
# 指南要点（基于公开共识整理，非个体化医嘱）
# ============================================================

GUIDES = {
    "gallstone": {
        "headline": "切除胆囊不是「不能吃油」，而是「不能一次吃太多油」。",
        "intro": (
            "胆囊的作用是储存和浓缩胆汁。切除后胆汁改为持续少量流入肠道，"
            "遇到一顿高脂大餐时没有足够的胆汁「突击」支援，未消化的脂肪进入结肠，"
            "就会出现腹胀、腹泻、油花样大便。绝大多数人在 3–6 个月内通过肠道适应自然缓解。"
        ),
        "diet": [
            {"t": "术后 4–6 周是适应期", "d": "脂肪供能比控制在 20–25%，优先植物油、深海鱼、坚果等不饱和来源；避免油炸、肥肉、奶油点心、动物皮。"},
            {"t": "少量多餐优于一日三大餐", "d": "把一天的脂肪总量分散到 4–5 餐，单餐脂肪越少，胆汁供需越容易匹配。"},
            {"t": "不需要终身严格低脂", "d": "适应期后逐步恢复常规饮食。长期过度限脂反而可能影响脂溶性维生素（A、D、E、K）吸收。"},
            {"t": "膳食纤维是长期盟友", "d": "可溶性纤维（燕麦、豆类、苹果、魔芋）能结合胆汁酸、改善腹泻，并降低胆汁酸在肠道的过度刺激。"},
            {"t": "警惕「隐性高脂」", "d": "坚果酱、沙拉酱、酥皮点心、奶茶、火锅蘸料，往往比一块瘦肉更容易触发症状。"},
            {"t": "限制酒精与含糖饮料", "d": "两者都会加重胆汁成分异常与肝脏脂质负担，是胆总管结石复发的可干预因素。"},
        ],
        "life": [
            {"t": "稳步减重，避免快速减重", "d": "每周减重超过 1.5 kg 会增加胆汁胆固醇饱和度，是结石形成的经典诱因。目标为每周 0.5–1 kg。"},
            {"t": "规律进食，不长时间空腹", "d": "空腹时间过长会使胆汁淤积、胆囊（或胆管）内压力升高。"},
            {"t": "餐后散步 15–20 分钟", "d": "促进胃肠蠕动与胆汁排空，对腹胀和胆汁反流有实际帮助。"},
        ],
        "watch": [
            {"t": "右上腹持续疼痛、发热、黄疸", "d": "三者同时出现提示胆管梗阻或胆管炎，需立即就医，不能观察等待。"},
            {"t": "持续水样腹泻超过 3 个月", "d": "可能是胆汁酸性腹泻，属于可治疗的问题，医生可用胆汁酸结合剂，不必硬扛。"},
            {"t": "油腻餐后反复右肩背放射痛", "d": "需排查胆总管残余结石或乳头功能障碍。"},
        ],
        "myths": [
            {"q": "切了胆囊就不能吃鸡蛋？", "a": "可以吃。蛋黄确实含脂肪，但同时富含卵磷脂与优质蛋白。关键是不要一次吃多个油炸蛋，水煮蛋通常耐受良好。"},
            {"q": "切了胆囊就不会再长结石？", "a": "不对。结石仍可能在胆总管内形成，发生率约 5–15%，所以长期饮食管理依然有意义。"},
        ],
    },
    "lipid": {
        "headline": "降 LDL 靠「换油」和「加纤维」，降甘油三酯靠「减糖」和「戒酒」——这是两条不同的路径。",
        "intro": (
            "血脂不是单一指标。低密度脂蛋白胆固醇（LDL-C）主要由饱和脂肪摄入和遗传决定，"
            "是动脉粥样硬化的直接推手；甘油三酯（TG）则高度受精制碳水、果糖和酒精影响。"
            "弄混这两条路径，是很多人「吃得很清淡但指标不降」的原因。"
        ),
        "diet": [
            {"t": "把饱和脂肪压到总能量 7% 以下", "d": "具体做法：换掉肥肉、猪油、黄油、椰子油、全脂奶制品，改吃菜籽油、橄榄油、亚麻籽油。"},
            {"t": "可溶性纤维每天 10 g 以上", "d": "约等于 60 g 燕麦 + 一份豆类。β-葡聚糖和果胶能结合胆汁酸、促进 LDL 清除，LDL 可降 5–10%。"},
            {"t": "植物甾醇 2 g/天", "d": "可再降 LDL 约 8–10%。强化植物甾醇的食用油或酸奶是现实来源。"},
            {"t": "每周 2 次深海鱼", "d": "三文鱼、鲭鱼、沙丁鱼提供 EPA/DHA，主要降低甘油三酯，对 TG 偏高者收益更明显。"},
            {"t": "严格限制添加糖与果糖", "d": "含糖饮料、果汁、蜂蜜、糕点中的果糖在肝脏直接转化为 TG。这一条对甘油三酯的影响大于对胆固醇的影响。"},
            {"t": "酒精是甘油三酯的强升因素", "d": "TG 偏高者建议完全戒酒；即使少量饮酒也可能使 TG 上升 20–30%。"},
            {"t": "用坚果替代零食，而不是额外加餐", "d": "每天 20–30 g 原味坚果有益，但热量密度高，需等量替换而非叠加。"},
        ],
        "life": [
            {"t": "每周 150 分钟中等强度有氧 + 2 次抗阻", "d": "运动主要提升 HDL、降低 TG，对 LDL 影响有限——这也说明为什么「光靠运动」降不了 LDL。"},
            {"t": "减重 5–10%", "d": "对 TG 和 HDL 改善最明显，对 LDL 的降幅通常只有 3–5%。"},
            {"t": "戒烟", "d": "吸烟降低 HDL 并加速 LDL 氧化，是独立于血脂数值的风险因素。"},
        ],
        "watch": [
            {"t": "TG ≥ 5.6 mmol/L", "d": "急性胰腺炎风险显著升高，需尽快就医，不能只靠饮食调整。"},
            {"t": "服药后出现肌肉酸痛、乏力", "d": "需查肌酸激酶，排除他汀相关肌病，不要自行停药或硬扛。"},
            {"t": "调脂治疗 4–12 周需复查", "d": "复查血脂 + 肝功能，评估疗效与耐受性，再决定是否调整方案。"},
        ],
        "myths": [
            {"q": "吃素血脂就一定正常？", "a": "不一定。精制碳水、油炸素食、椰子油制品同样会推高 TG 和 LDL。关键在脂肪类型与碳水质量，而非「有没有肉」。"},
            {"q": "胆固醇吃多了才血脂高？", "a": "膳食胆固醇的影响远小于饱和脂肪与遗传。多数人每天 1 个鸡蛋无碍，真正要盯的是饱和脂肪和总能量。"},
        ],
    },
    "uric": {
        "headline": "升尿酸最猛的不是海鲜，是含糖饮料和酒。",
        "intro": (
            "尿酸是嘌呤代谢的终产物。约 2/3 来自体内自身合成，1/3 来自食物。"
            "果糖在肝脏代谢时会消耗 ATP、加速嘌呤分解，同时竞争性抑制尿酸排泄——"
            "这是含糖饮料比多数海鲜更能推高尿酸的原因。"
        ),
        "diet": [
            {"t": "严格限制高嘌呤动物性食物", "d": "动物内脏、浓肉汤/火锅老汤、沙丁鱼、凤尾鱼、贝类。红肉每日不超过 100 g。"},
            {"t": "含糖饮料与果汁要断", "d": "包括「鲜榨」果汁和蜂蜜水。果糖的双重机制（生成增加 + 排泄减少）使其成为最强饮食因素之一。"},
            {"t": "酒精，尤其啤酒和白酒", "d": "啤酒既含嘌呤又含酒精，是痛风发作的经典诱因；发作期应完全避免。"},
            {"t": "每天饮水 2000–3000 ml", "d": "心、肾功能正常者适用。分次饮用，尿液保持清淡色，有助于尿酸排出与预防尿酸结石。"},
            {"t": "低脂乳制品有保护作用", "d": "牛奶、无糖酸奶可促进尿酸排泄，是少数「可主动增加」的食物类别。"},
            {"t": "豆制品不必一概禁止", "d": "这是过时观念。植物嘌呤对血尿酸影响远小于动物嘌呤，豆腐、豆浆可适量食用。"},
            {"t": "蔬菜、樱桃、咖啡可正常吃", "d": "蔬菜总体不升尿酸；樱桃与咖啡有弱的降尿酸证据，属「有益无害」，但不足以替代治疗。"},
        ],
        "life": [
            {"t": "避免剧烈运动与脱水", "d": "一次性高强度运动使 ATP 大量分解、乳酸堆积抑制尿酸排泄，是常见的发作诱因。中等强度有氧更安全。"},
            {"t": "避免受凉与关节外伤", "d": "温度下降使尿酸盐更易析出结晶，夜间足部保暖有实际意义。"},
            {"t": "减重但避免饥饿式减重", "d": "快速减重与生酮饮食会升高血尿酸，需平稳推进。"},
        ],
        "watch": [
            {"t": "急性发作期不加用降尿酸药", "d": "通常待急性期缓解 2–4 周后再启动，否则血尿酸波动可能加重发作。具体时机由医生决定。"},
            {"t": "目标值：< 360 μmol/L", "d": "有痛风石者需 < 300 μmol/L。达标后仍需维持，不可自行停药。"},
            {"t": "关节红肿热痛伴发热", "d": "需与化脓性关节炎、蜂窝织炎鉴别，不能一律按痛风处理。"},
        ],
        "myths": [
            {"q": "不吃海鲜内脏，尿酸就能正常？", "a": "多数人不行。内源性合成占 2/3，饮食干预通常只能降 60–90 μmol/L。是否用药取决于基线水平和是否有痛风/结石。"},
            {"q": "痛风不痛了就可以停药？", "a": "不对。疼痛消失只代表炎症消退，尿酸盐结晶仍在沉积。擅自停药是复发和痛风石形成的主因。"},
        ],
    },
    "pancreas": {
        "headline": "胰腺脂肪浸润是可逆的——减重是目前证据最强的干预。",
        "intro": (
            "胰腺脂肪浸润（脂肪胰）指脂肪在胰腺实质内异常沉积，常与肥胖、"
            "内脏脂肪堆积、高甘油三酯、酒精摄入并存。它本身多无症状，"
            "但长期可影响胰腺外分泌功能（消化吸收）与内分泌功能（血糖调节），"
            "也是胰腺炎风险的背景因素。好消息是：随着体重和甘油三酯下降，"
            "影像上的脂肪沉积可以明显减少。"
        ),
        "diet": [
            {"t": "减重是核心，不是辅助", "d": "减重 5–10% 即可显著降低胰腺脂肪含量。这是目前所有干预中证据最一致的。"},
            {"t": "严格限酒，最好戒酒", "d": "酒精对胰腺腺泡细胞有直接毒性，且与脂肪浸润协同损伤，是胰腺炎最强的可控危险因素。"},
            {"t": "把甘油三酯压到 2.3 mmol/L 以下", "d": "TG > 5.6 mmol/L 时急性胰腺炎风险陡增。控糖、戒酒、减重、必要时用药，缺一不可。"},
            {"t": "避免单次高脂大餐", "d": "一次大量脂肪会刺激胆囊收缩素大量释放、胰酶分泌骤增，对已有脂肪浸润的胰腺是额外负荷。"},
            {"t": "脂肪泻时考虑中链甘油三酯（MCT）", "d": "MCT 不需要脂肪酶和胆盐参与即可吸收，可作为部分脂肪替代。需在医生或营养师指导下使用。"},
            {"t": "关注脂溶性维生素", "d": "若存在胰腺外分泌功能不全，维生素 A、D、E、K 吸收会受影响，必要时检测并补充。"},
        ],
        "life": [
            {"t": "有氧 + 抗阻结合", "d": "抗阻训练增加骨骼肌量、改善胰岛素敏感性，对减少异位脂肪沉积有独立价值。"},
            {"t": "控制血糖与胰岛素抵抗", "d": "胰岛素抵抗是脂肪异位沉积的重要机制，控糖本身就是护胰。"},
            {"t": "定期影像随访", "d": "腹部超声敏感度有限，MRI-PDFF 或超声内镜（EUS）更能定量评估脂肪含量，随访方案由医生制定。"},
        ],
        "watch": [
            {"t": "脂肪泻、体重下降、饭后腹胀", "d": "提示胰腺外分泌功能不全，需检测粪弹性蛋白酶，可能需要胰酶替代治疗。"},
            {"t": "持续上腹痛并向背部放射", "d": "警惕慢性胰腺炎或急性发作，需及时就诊。"},
            {"t": "新发血糖升高或难以控制", "d": "胰腺内分泌功能受损的表现，需评估是否为胰源性糖尿病（3c 型）。"},
        ],
        "myths": [
            {"q": "脂肪胰只是「影像上的小问题」？", "a": "不是。它与代谢综合征、胰腺外分泌功能不全、胰腺炎风险相关，且是可干预的，值得认真对待。"},
            {"q": "只要不吃油就能改善？", "a": "不准确。关键在总能量与体重、酒精、甘油三酯。单纯把油减到极低而不减重，脂肪浸润不会明显改善。"},
        ],
    },
}

DISCLAIMER = (
    "以上内容整理自公开的临床指南与共识（如《中国血脂管理指南》《中国高尿酸血症与痛风诊疗指南》、"
    "AGA/ESGE 相关综述等），仅作健康科普与生活方式参考，不构成诊断或处方建议。"
    "个体情况（尤其合并用药、肝肾功能、术后并发症）差异较大，具体方案请由你的主诊医生确定。"
)


# ============================================================
# Europe PMC 循证文献
# ============================================================

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def match_topics(text: str) -> list:
    """返回命中的主题 id 列表。"""
    hits = []
    low = text.lower()
    for t in TOPICS:
        for kw in t["keywords"]:
            if kw.lower() in low:
                hits.append(t["id"])
                break
    return hits


def route_health_item(item: dict) -> str:
    """给一条健康资讯打主题标签；未命中任何主题返回空串（将被丢弃）。"""
    blob = f"{item.get('raw_title','')} {item.get('raw_summary','')[:400]}"
    hits = match_topics(blob)
    return hits[0] if hits else ""


def fetch_epmc(topic: dict, page_size: int = 6, _retry: int = 3) -> list:
    """抓取某主题的综述/指南类文献。限流时退避重试（2/4/6 秒）。"""
    params = {
        "query": topic["epmc_query"],
        "format": "json",
        "pageSize": str(page_size),
        "resultType": "core",
        "sort": "CITED desc",
        # Europe PMC 要求标明调用方身份，否则偶尔返回 "INVALID EMAIL PROVIDED"
        "email": "signal-tower@users.noreply.github.com",
        "tool": "signal-tower",
    }
    url = EPMC + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "SignalTower/1.0"})
    data = None
    for attempt in range(_retry + 1):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            break
        except Exception as e:  # noqa: BLE001
            if attempt >= _retry:
                print(f"[epmc] {topic['id']} 抓取失败: {type(e).__name__}")
                return []
            time.sleep(2 * (attempt + 1))

    if not data:
        return []

    out = []
    for rec in (data.get("resultList") or {}).get("result", []):
        title = (rec.get("title") or "").strip().rstrip(".")
        # 接口限流时会用占位文本顶替，必须挡掉
        if not title or "INVALID" in title.upper() or len(title) < 12:
            continue
        abstract = fetcher.strip_html(rec.get("abstractText") or "")
        if "INVALID" in abstract.upper()[:40]:
            abstract = ""
        journal = ((rec.get("journalInfo") or {}).get("journal") or {}).get("title") or ""
        year = rec.get("pubYear") or ""
        doi = rec.get("doi") or ""
        pmid = rec.get("pmid") or ""
        link = f"https://doi.org/{doi}" if doi else (
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        )
        if not link:
            continue
        out.append(
            {
                "raw_title": title,
                "url": link,
                "guid": doi or pmid or title,
                "raw_summary": abstract[:900],
                "published": _year_ts(year),
                "source_id": "epmc",
                "source_name": f"Europe PMC · {journal[:28]}" if journal else "Europe PMC",
                "category": "health",
                "lang": "en",
                "weight": 0.85,
                "topic": topic["id"],
                "journal": journal,
                "year": year,
                "kind": "paper",
            }
        )
    return out


def _year_ts(year) -> float:
    try:
        return time.mktime(time.strptime(f"{int(year)}-01-15", "%Y-%m-%d"))
    except (ValueError, TypeError):
        return 0.0


def fetch_all_epmc(per_topic: int = 6, ttl_hours: float = 12) -> list:
    """
    按主题抓取，主题之间留间隔。
    曾用并发，但 EPMC 对突发请求敏感，会返回占位错误文本。

    缓存按主题分别存：文献以月为单位更新，没必要每次构建都去打扰它。
    高频构建时命中缓存，既省时间，也避免限流导致某一栏文献忽有忽无。
    某个主题抓取失败时沿用该主题的旧结果，而不是让整栏空掉。
    """
    cache = _load_epmc_cache()
    topics_cache = cache.get("topics", {})
    now = time.time()

    out = []
    touched = False
    for i, t in enumerate(TOPICS):
        tid = t["id"]
        entry = topics_cache.get(tid) or {}
        fresh = entry.get("ts") and now - entry["ts"] < ttl_hours * 3600
        if fresh and entry.get("items"):
            out.extend(entry["items"])
            continue

        if i:
            time.sleep(1.8)
        got = fetch_epmc(t, per_topic)
        if got:
            topics_cache[tid] = {"ts": now, "items": got}
            touched = True
            out.extend(got)
        elif entry.get("items"):
            # 抓取失败但有旧数据 —— 用旧的，别让主题消失
            print(f"[epmc] {tid} 抓取失败，沿用旧缓存（{len(entry['items'])} 条）")
            out.extend(entry["items"])
        else:
            print(f"[epmc] {tid} 无数据也无缓存，本栏暂缺")
        time.sleep(0.6)

    if touched:
        _save_epmc_cache({"version": 2, "topics": topics_cache})
    return out


def _epmc_cache_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "epmc.json")


def _load_epmc_cache() -> dict:
    try:
        with open(_epmc_cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    # 旧版是 {"ts":..., "items":[...]}，结构不同直接丢弃重抓
    return data if isinstance(data, dict) and data.get("version") == 2 else {}


def _save_epmc_cache(payload: dict) -> None:
    path = _epmc_cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except OSError:
        pass


def score_health(item: dict, now: float) -> float:
    """健康条目的打分：主题命中 + 来源权重 + 时效。"""
    import filtering

    s = item["weight"] * 50
    s += filtering.title_quality(item["raw_title"])
    s += filtering.summary_quality(item.get("raw_summary") or "") * 0.6
    if item.get("kind") == "paper":
        s += 6          # 循证内容给固定加成
    else:
        s += filtering.freshness_score(item.get("published"), now)
    if "胰腺" in item["raw_title"]:
        s += 2
    return s
