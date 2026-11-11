# -*- coding: utf-8 -*-
"""
翻译层 —— 英文源转中文。

双引擎：
  · llm    ：配置了 API Key 时启用，整段意群翻译，术语准确、不增删
  · free   ：零配置兜底，走 MyMemory 公共接口（分句 + 术语还原）

两者都过同一个"术语校正"环节，把机翻常错的专有名词拉回原文。
"""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "translate.json")
_lock = threading.Lock()
_cache = {}
_dirty = 0

# 机翻常见误译 → 正确写法。这是"不绕弯子"的关键：专名必须原样。
TERM_FIX = [
    (r"克劳德", "Claude"),
    (r"聊天\s*GPT", "ChatGPT"),
    (r"开放\s*AI|开放人工智能", "OpenAI"),
    (r"深度求索", "DeepSeek"),
    (r"双子座|杰米尼", "Gemini"),
    (r"骆驼|羊驼", "Llama"),
    (r"米斯特拉尔", "Mistral"),
    (r"英伟达", "英伟达"),
    (r"图形处理器|图形处理单元", "GPU"),
    (r"大型语言模型", "大语言模型"),
    (r"人工智能生成内容", "AIGC"),
    (r"思维链", "思维链"),
    (r"脸书|Facebook公司", "Meta"),
    (r"字母表公司|字母表", "Alphabet"),
    (r"微软公司", "微软"),
    (r"苹果公司", "苹果"),
    (r"亚马逊公司", "亚马逊"),
    (r"特斯拉公司", "特斯拉"),
    (r"芯片巨头英伟达", "英伟达"),
]
TERM_RE = [(re.compile(p), r) for p, r in TERM_FIX]

MYMEMORY = "https://api.mymemory.translated.net/get"
GOOGLE = "https://translate.googleapis.com/translate_a/single"

_probe_lock = threading.Lock()
_google_ok = None      # None = 未探测, True/False = 结论


def _load():
    global _cache
    if _cache:
        return
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (OSError, ValueError):
        _cache = {}


def _save(force=False):
    global _dirty
    if not force and _dirty < 20:
        return
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
        os.replace(tmp, CACHE_PATH)
        _dirty = 0
    except OSError:
        pass


def key_of(text: str) -> str:
    return sha1(text.encode("utf-8")).hexdigest()[:20]


def fix_terms(text: str) -> str:
    for rx, repl in TERM_RE:
        text = rx.sub(repl, text)
    # 收拾机翻留下的空格与标点毛病
    text = re.sub(r"\s+([，。；：！？])", r"\1", text)
    text = re.sub(r"([（【])\s+", r"\1", text)
    text = re.sub(r"\s+([）】])", r"\1", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    return text.strip()


def needs_translation(text: str) -> bool:
    if not text:
        return False
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return cjk < max(2, len(text) * 0.12) and latin > 6


# 翻译接口在限流/出错时会把这些当成"译文"返回，必须挡掉
BAD_MARKERS = (
    "INVALID EMAIL",
    "MYMEMORY WARNING",
    "QUERY LENGTH LIMIT",
    "TOO MANY REQUESTS",
    "RATE LIMIT",
    "SERVICE UNAVAILABLE",
    "NO QUERY SPECIFIED",
)


def is_bad_translation(out: str, src: str) -> bool:
    """判断返回值是不是接口的错误占位，而不是真正的译文。"""
    if not out:
        return True
    u = out.upper()
    su = src.upper()
    for m in BAD_MARKERS:
        if m in u and m not in su:
            return True
    # 中文译文里必须真的有汉字，否则说明没翻成
    if not any("\u4e00" <= c <= "\u9fff" for c in out):
        return True
    return False


# ---------------- 免费引擎 ----------------

def _google_one(text: str, timeout: int = 14) -> str:
    """Google 翻译非官方端点。GitHub Actions（境外）可用，境内通常不通。"""
    payload = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text}
    ).encode()
    url = f"{GOOGLE}?client=gtx&sl=auto&tl=zh-CN&dt=t"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    segs = data[0] if data and isinstance(data[0], list) else []
    out = "".join(s[0] for s in segs if s and s[0])
    if is_bad_translation(out, text):
        return ""
    return fix_terms(out)


def probe_google() -> bool:
    """探测一次 Google 端点，结果全局缓存（进程内只探一次）。"""
    global _google_ok
    if _google_ok is not None:
        return _google_ok
    with _probe_lock:
        if _google_ok is not None:
            return _google_ok
        try:
            got = _google_one("Hello world.", timeout=8)
            _google_ok = bool(got and any("\u4e00" <= c <= "\u9fff" for c in got))
        except Exception:  # noqa: BLE001
            _google_ok = False
        print(f"[translate] Google 端点探测: {'可用' if _google_ok else '不可用，回退 MyMemory'}")
        return _google_ok


def _free_one(text: str, timeout: int = 12, retry: int = 2) -> str:
    """MyMemory 单条翻译。限流很敏感，失败后退避重试。"""
    q = urllib.parse.quote(text[:480])
    url = f"{MYMEMORY}?q={q}&langpair=en|zh-CN"
    req = urllib.request.Request(url, headers={"User-Agent": "SignalTower/1.0"})
    for attempt in range(retry + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            out = (data.get("responseData") or {}).get("translatedText") or ""
            if is_bad_translation(out, text):
                raise ValueError("bad translation")
            if out.strip() == text.strip():
                return ""
            return fix_terms(out)
        except Exception:  # noqa: BLE001
            if attempt >= retry:
                return ""
            time.sleep(0.8 * (attempt + 1))
    return ""


def _split_sentences(text: str, limit: int = 420) -> list:
    parts = re.split(r"(?<=[.!?;:])\s+", text)
    chunks, cur = [], ""
    for p in parts:
        if len(cur) + len(p) + 1 <= limit:
            cur = (cur + " " + p).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks or [text[:limit]]


def _free_translate(text: str) -> str:
    if probe_google():
        chunks = _split_sentences(text, limit=1600)
        with ThreadPoolExecutor(max_workers=4) as pool:
            outs = list(pool.map(lambda c: _safe(_google_one, c), chunks))
        return "".join(outs).strip()
    # MyMemory：严格串行 + 间隔，它对突发请求会直接拒答
    chunks = _split_sentences(text, limit=420)
    outs = []
    for i, c in enumerate(chunks):
        if i:
            time.sleep(0.12)
        outs.append(_safe(_free_one, c))
    return "".join(outs).strip()


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return ""


# ---------------- LLM 引擎 ----------------

LLM_PROMPT = (
    "你是专业的科技与新闻译者。把下面的英文翻译成简体中文。"
    "硬性要求：\n"
    "1. 直译忠实，不增删、不解释、不总结、不添加原文没有的内容。\n"
    "2. 专有名词保留英文原样（公司名、模型名、人名、产品名、论文标题）。\n"
    "3. 数字、单位、引语必须与原文字面一致。\n"
    "4. 技术术语用中文业界通用译法，括号内保留英文缩写。\n"
    "5. 只输出译文，不要任何前后缀、不要 markdown 代码块。\n\n"
)


def _llm_translate(texts: list, cfg: dict) -> list:
    """一次 API 调用翻一批，用编号对齐，避免错位。"""
    numbered = "\n\n".join(f"<<<{i+1}>>>\n{t}" for i, t in enumerate(texts))
    body = {
        "model": cfg.get("model") or "deepseek-chat",
        "temperature": 0.2,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": LLM_PROMPT},
            {"role": "user", "content": numbered + f"\n\n请按 <<<1>>> ... <<<{len(texts)}>>> 的编号顺序输出译文。"},
        ],
    }
    base = (cfg.get("base_url") or "").rstrip("/")
    url = base + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.get('api_key','')}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    content = data["choices"][0]["message"]["content"].strip()
    # 按编号切分
    slots = re.split(r"<<<\s*(\d+)\s*>>>", content)
    out = [""] * len(texts)
    for i in range(1, len(slots) - 1, 2):
        try:
            idx = int(slots[i]) - 1
        except ValueError:
            continue
        if 0 <= idx < len(out):
            out[idx] = fix_terms(slots[i + 1].strip())
    return out


# ---------------- 对外接口 ----------------

class Translator:
    def __init__(self, llm_cfg: dict | None = None):
        self.cfg = dict(llm_cfg or {})
        # 环境变量优先（GitHub Actions 用 Secrets 注入）
        env_key = os.environ.get("LLM_API_KEY", "").strip()
        if env_key:
            self.cfg["enabled"] = True
            self.cfg["api_key"] = env_key
            if os.environ.get("LLM_BASE_URL"):
                self.cfg["base_url"] = os.environ["LLM_BASE_URL"]
            if os.environ.get("LLM_MODEL"):
                self.cfg["model"] = os.environ["LLM_MODEL"]
        self.enabled = bool(self.cfg.get("enabled") and self.cfg.get("api_key"))
        _load()

    @property
    def engine(self):
        if self.enabled:
            return "llm"
        return "google" if probe_google() else "mymemory"

    def translate(self, text: str) -> str:
        """单条翻译，带缓存。失败返回空串（调用方回退原文）。"""
        text = (text or "").strip()
        if not text or not needs_translation(text):
            return ""
        k = key_of(text)
        if k in _cache:
            return _cache[k]
        out = ""
        if self.enabled:
            try:
                got = _llm_translate([text], self.cfg)
                out = got[0] if got else ""
            except Exception:  # noqa: BLE001
                out = ""
        if not out:
            out = _safe(_free_translate, text)
        if out and is_bad_translation(out, text):
            out = ""
        if out:
            global _dirty
            with _lock:
                _cache[k] = out
                _dirty += 1
            _save()
        return out

    def translate_many(self, texts: list, workers: int = 4) -> dict:
        """批量翻译，返回 {原文: 译文}。已缓存的直接命中。"""
        result, todo = {}, []
        for t in texts:
            t = (t or "").strip()
            if not t or not needs_translation(t):
                continue
            k = key_of(t)
            if k in _cache:
                result[t] = _cache[k]
            else:
                todo.append(t)
        if not todo:
            return result

        if self.enabled:
            batch = 12
            chunks = [todo[i : i + batch] for i in range(0, len(todo), batch)]
            with ThreadPoolExecutor(max_workers=3) as pool:
                for ch, outs in zip(chunks, pool.map(lambda c: _safe_list(self, c), chunks)):
                    for src, dst in zip(ch, outs):
                        if dst and not is_bad_translation(dst, src):
                            result[src] = dst
        else:
            outs = []
            for i, t in enumerate(todo):
                if i:
                    time.sleep(0.1)
                outs.append(_safe(_free_translate, t))
            for src, dst in zip(todo, outs):
                if dst and not is_bad_translation(dst, src):
                    result[src] = dst

        if result:
            global _dirty
            with _lock:
                for src, dst in result.items():
                    if dst and not is_bad_translation(dst, src):
                        _cache[key_of(src)] = dst
                _dirty += len(result)
            _save(force=True)
        return result

    def stats(self):
        return {"engine": self.engine, "cached": len(_cache)}


def _safe_list(self, chunk):
    try:
        return _llm_translate(chunk, self.cfg)
    except Exception:  # noqa: BLE001
        return _safe_list_free(chunk)


def _safe_list_free(chunk):
    return [_safe(_free_translate, t) for t in chunk]
