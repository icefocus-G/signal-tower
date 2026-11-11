# -*- coding: utf-8 -*-
"""
信号塔 · 服务端
================
零依赖 HTTP 服务。启动后后台自动聚合，前端轮询拿结果。
"""
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import fetcher
import filtering
import health as H
import pipeline
import sources as S
from translate import Translator

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")
CACHE_DIR = os.path.join(BASE, "cache")
CONFIG_PATH = os.path.join(BASE, "config.json")
FEED_CACHE = os.path.join(CACHE_DIR, "feed.json")
ARTICLE_CACHE = os.path.join(CACHE_DIR, "articles.json")

REFRESH_MINUTES = 20

DEFAULT_CONFIG = {
    "port": 8890,
    "refresh_minutes": 20,
    "max_items_per_category": 90,
    "max_age_hours": 120,
    "llm": {
        "enabled": False,
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
    },
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except (OSError, ValueError) as e:
            print(f"[config] 读取失败，用默认值: {e}")
    else:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    return cfg


class Store:
    """全局状态：聚合结果 + 后台刷新。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.translator = Translator(cfg.get("llm"))
        self.data = {"ai": [], "politics": [], "health": []}
        self.stats = {"ai": {}, "politics": {}}
        self.source_status = {}
        self.updated_at = 0
        self.refreshing = False
        self.last_error = ""
        self.articles = {}
        self._load_feed_cache()
        self._load_article_cache()

    # -------- 缓存 --------
    def _load_feed_cache(self):
        try:
            with open(FEED_CACHE, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.data = d.get("data", self.data)
            self.stats = d.get("stats", self.stats)
            self.source_status = d.get("source_status", {})
            self.updated_at = d.get("updated_at", 0)
        except (OSError, ValueError):
            pass

    def _save_feed_cache(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = FEED_CACHE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "data": self.data,
                        "stats": self.stats,
                        "source_status": self.source_status,
                        "updated_at": self.updated_at,
                    },
                    f,
                    ensure_ascii=False,
                )
            os.replace(tmp, FEED_CACHE)
        except OSError:
            pass

    def _load_article_cache(self):
        try:
            with open(ARTICLE_CACHE, "r", encoding="utf-8") as f:
                self.articles = json.load(f)
        except (OSError, ValueError):
            self.articles = {}

    def _save_article_cache(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = ARTICLE_CACHE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.articles, f, ensure_ascii=False)
            os.replace(tmp, ARTICLE_CACHE)
        except OSError:
            pass

    # -------- 聚合 --------
    def refresh(self):
        if self.refreshing:
            return
        self.refreshing = True
        t0 = time.time()
        try:
            result = pipeline.aggregate(
                self.cfg, with_articles=0, translator=self.translator
            )
            with self.lock:
                self.data = result["data"]
                self.stats = result["stats"]
                self.source_status = result["sources"]["status"]
                self.updated_at = result["generated_at"]
                self.last_error = ""
            self._save_feed_cache()
            print(
                f"[refresh] {time.time()-t0:.1f}s  "
                + "  ".join(f"{k}:{len(v)}" for k, v in self.data.items())
                + f"  引擎={result['engine']}"
            )
        except Exception as e:  # noqa: BLE001
            self.last_error = f"{type(e).__name__}: {e}"
            print("[refresh] 失败:", self.last_error)
            traceback.print_exc()
        finally:
            self.refreshing = False

    def _translate_feed(self, grouped):
        """翻译英文条目的标题与摘要（限长，详情页再整篇翻）。"""
        pending = []
        for cat, items in grouped.items():
            for it in items:
                if it["lang"] == "en":
                    it["title_orig"] = it["title"]
                    if it.get("summary"):
                        it["summary_orig"] = it["summary"]
                    pending.append(it["title"])
                    if it.get("summary"):
                        pending.append(it["summary"][:260])
        if not pending:
            return
        try:
            mapping = self.translator.translate_many(pending, workers=4)
        except Exception as e:  # noqa: BLE001
            print("[translate] 批量失败:", e)
            mapping = {}

        for cat, items in grouped.items():
            for it in items:
                if it["lang"] != "en":
                    continue
                t = mapping.get(it["title"])
                if t:
                    it["title"] = t
                    it["translated"] = True
                else:
                    it["translated"] = False
                s = mapping.get((it.get("summary") or "")[:260])
                if s:
                    it["summary"] = s

    # -------- 详情 --------
    def get_article(self, aid: str):
        if aid in self.articles:
            return self.articles[aid]
        target = None
        for items in self.data.values():
            for it in items:
                if it["id"] == aid:
                    target = it
                    break
        if not target:
            return None
        return self._build_article(target)

    def _build_article(self, item):
        url = item["url"]
        body, err = "", ""
        try:
            page = fetcher.http_get(url, timeout=20)
            body = fetcher.extract_article(page)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            err = f"正文抓取失败：{type(e).__name__}"
        except Exception as e:  # noqa: BLE001
            err = f"正文抓取失败：{type(e).__name__}"

        art = {
            "id": item["id"],
            "title": item["title"],
            "title_orig": item.get("title_orig", ""),
            "summary": item.get("summary", ""),
            "summary_orig": item.get("summary_orig", ""),
            "body": body,
            "body_orig": "",
            "translated_body": False,
            "source": item["source_name"],
            "url": url,
            "published": item.get("published"),
            "lang": item["lang"],
            "error": err,
        }
        if item["lang"] == "en" and body:
            art["body_orig"] = body
            zh = self._translate_body(body)
            if zh:
                art["body"] = zh
                art["translated_body"] = True
        self.articles[item["id"]] = art
        self._save_article_cache()
        return art

    def _translate_body(self, body: str) -> str:
        """长文分段翻译，控制单次请求量。"""
        if not body:
            return ""
        paras = [p for p in body.split("\n\n") if p.strip()]
        # 太长就截断，避免翻爆配额
        acc, total = [], 0
        for p in paras:
            if total + len(p) > 6000:
                break
            acc.append(p)
            total += len(p)
        mapping = self.translator.translate_many(acc, workers=4)
        if not mapping:
            return ""
        out = []
        for p in acc:
            out.append(mapping.get(p, p if not self.translator else ""))
        text = "\n\n".join(x for x in out if x)
        return text


CFG = load_config()
STORE = Store(CFG)


def background_loop():
    interval = max(5, int(CFG.get("refresh_minutes", REFRESH_MINUTES))) * 60
    while True:
        try:
            STORE.refresh()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(interval)


MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "SignalTower/1.0"

    def log_message(self, fmt, *args):  # 安静一点，只打错误
        if not str(args[1] if len(args) > 1 else "").startswith("2"):
            pass

    # ---- helpers ----
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404, "not found")
            return
        ext = os.path.splitext(path)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ---- routes ----
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path

        try:
            if path == "/api/feed":
                return self._api_feed(q)
            if path == "/api/article":
                return self._api_article(q)
            if path == "/api/sources":
                return self._json(
                    {
                        "sources": S.SOURCES,
                        "status": STORE.source_status,
                        "translator": STORE.translator.stats(),
                    }
                )
            if path == "/api/health":
                return self._json(
                    {
                        "ok": True,
                        "refreshing": STORE.refreshing,
                        "updated_at": STORE.updated_at,
                        "error": STORE.last_error,
                        "translator": STORE.translator.stats(),
                    }
                )
            if path == "/api/refresh":
                if not STORE.refreshing:
                    threading.Thread(target=STORE.refresh, daemon=True).start()
                return self._json({"started": True})
            # 静态文件
            if path in ("/", "/index.html"):
                return self._file(os.path.join(STATIC, "index.html"))
            safe = os.path.normpath(path).lstrip("/")
            fp = os.path.join(STATIC, safe)
            if fp.startswith(STATIC) and os.path.isfile(fp):
                return self._file(fp)
            return self.send_error(404, "not found")
        except BrokenPipeError:
            pass
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            try:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            except Exception:  # noqa: BLE001
                pass

    def _api_feed(self, q):
        cat = (q.get("category") or ["ai"])[0]
        if cat not in ("ai", "politics", "health"):
            cat = "ai"
        with STORE.lock:
            items = STORE.data.get(cat, [])
            stats = STORE.stats.get(cat, {})
        payload = {
            "category": cat,
            "items": items,
            "stats": stats,
            "updated_at": STORE.updated_at,
            "refreshing": STORE.refreshing,
            "error": STORE.last_error,
            "translator": STORE.translator.stats(),
        }
        if cat == "health":
            payload["topics"] = [
                {"id": t["id"], "name": t["name"], "short": t["short"]} for t in H.TOPICS
            ]
            payload["guides"] = H.GUIDES
            payload["disclaimer"] = H.DISCLAIMER
        self._json(payload)

    def _api_article(self, q):
        aid = (q.get("id") or [""])[0]
        if not re.fullmatch(r"[0-9a-f]{6,32}", aid):
            return self._json({"error": "bad id"}, 400)
        art = STORE.get_article(aid)
        if not art:
            return self._json({"error": "未找到该条目"}, 404)
        self._json(art)


def main():
    port = int(os.environ.get("PORT") or CFG.get("port", 8890))

    # 端口被占用时自动顺延，避免启动失败
    srv = None
    for candidate in range(port, port + 12):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if srv is None:
        print(f"错误：{port}-{port+11} 端口都被占用，请设置 PORT 环境变量")
        sys.exit(1)

    threading.Thread(target=background_loop, daemon=True).start()
    print("=" * 56)
    print("  信号塔 · 前沿 AI / 时政 / 养生")
    print(f"  http://127.0.0.1:{port}")
    print(f"  翻译引擎: {'LLM' if STORE.translator.enabled else '免费接口（可在 config.json 配 Key 升级）'}")
    print(f"  源数量: {len(S.SOURCES)}   刷新间隔: {CFG.get('refresh_minutes')} 分钟")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        STORE._save_feed_cache()
        sys.exit(0)


if __name__ == "__main__":
    main()
