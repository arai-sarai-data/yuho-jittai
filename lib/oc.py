"""全サイト共通の取得・検証・出力ヘルパー。

方針
- 公式の配布ファイル/APIだけを使う。アクセスは間隔を空け、User-Agentで連絡先を名乗る。
- 想定と違う形式のデータが来たら、推測で埋めずに例外で止める（＝古い正しいデータが残る）。
- 出力は docs/data/ 以下の JSON のみ。
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"          # ダウンロードしたファイル（コミットしない）
OUT = ROOT / "docs" / "data"
RAW.mkdir(exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

REPO = os.environ.get("GITHUB_REPOSITORY", "")
UA = "arai-sarai-data opendata bot (+https://github.com/%s)" % (REPO or "arai-sarai-data")
WAIT = float(os.environ.get("OC_WAIT", "1.5"))   # 同一サイトへの連続アクセス間隔（秒）

_session = requests.Session()
_session.headers["User-Agent"] = UA
_last = {}


class DataError(Exception):
    """元データが想定どおりでない。公開を止める。"""


def check(cond, msg):
    if not cond:
        raise DataError(msg)


def log(*a):
    print("[%s]" % _dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def _polite(url):
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    t = _last.get(host, 0)
    d = time.time() - t
    if d < WAIT:
        time.sleep(WAIT - d)
    _last[host] = time.time()


def get(url, params=None, headers=None, cache=None, retries=4, timeout=120, as_json=False):
    """GET。cache にファイル名を渡すと raw/ に保存し、次回はそれを使う。"""
    if cache:
        p = RAW / "cache" / cache
        if p.exists() and p.stat().st_size > 0:
            b = p.read_bytes()
            return json.loads(b) if as_json else b
    err = None
    for i in range(retries):
        _polite(url)
        try:
            r = _session.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError("HTTP %s" % r.status_code)
            r.raise_for_status()
            b = r.content
            if cache:
                (RAW / "cache" / cache).parent.mkdir(parents=True, exist_ok=True)
                (RAW / "cache" / cache).write_bytes(b)
            return r.json() if as_json else b
        except Exception as e:  # noqa
            err = e
            log("retry", i + 1, url, e)
            time.sleep(5 * (i + 1))
    raise DataError("取得に失敗: %s (%s)" % (url, err))


def links(page_url, pattern, html=None):
    """ページ内のリンクのうち pattern(正規表現) に合うものを絶対URLで返す（出現順・重複なし）。"""
    if html is None:
        html = decode(get(page_url))
    out = []
    for m in re.finditer(r'href\s*=\s*["\']([^"\']+)["\']', html, re.I):
        u = urljoin(page_url, m.group(1).strip())
        if re.search(pattern, u) and u not in out:
            out.append(u)
    return out


def anchors(page_url, pattern, html=None):
    """ページ内の <a> のうち href が pattern に合うものを [(絶対URL, リンク文字列, 直前の文字列)] で返す。"""
    if html is None:
        html = decode(get(page_url))
    out, seen = [], set()
    for m in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        u = urljoin(page_url, m.group(1).strip())
        if not re.search(pattern, u) or u in seen:
            continue
        seen.add(u)
        text = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
        before = re.sub(r"<[^>]+>|\s+", " ", html[max(0, m.start() - 400):m.start()]).strip()[-120:]
        out.append((u, text, before))
    return out


def decode(b: bytes) -> str:
    for enc in ("utf-8-sig", "cp932", "euc_jp"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def read_csv(b: bytes, **kw):
    import pandas as pd
    last = None
    for enc in ("utf-8-sig", "cp932"):
        try:
            return pd.read_csv(io.BytesIO(b), encoding=enc, dtype=str, keep_default_na=False, **kw)
        except UnicodeDecodeError as e:
            last = e
    raise DataError("CSVの文字コードを判定できません: %s" % last)


def unzip(b: bytes):
    """zip の中身を {名前: bytes} で返す（日本語ファイル名の文字化け対策つき）。"""
    out = {}
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not (info.flag_bits & 0x800):
                try:
                    name = name.encode("cp437").decode("cp932")
                except Exception:
                    pass
            out[name] = z.read(info)
    return out


def col(df, *keys, required=True):
    """列名に keys のすべてを含む列を1つ探す（全角半角・空白の違いは無視）。"""
    def n(s):
        s = str(s).replace("　", "").replace(" ", "")
        return s.translate(str.maketrans("（）", "()"))
    cands = [c for c in df.columns if all(n(k) in n(c) for k in keys)]
    if not cands:
        if required:
            raise DataError("列が見つかりません: %s / 実際の列: %s" % (keys, list(df.columns)[:60]))
        return None
    return cands[0]


def num(s):
    """'1,234' '－' '' などを float/None に。"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace(",", "").replace("，", "")
    if t in ("", "-", "－", "―", "‐", "*", "＊", "x", "X", "…", "nan", "None"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


PREF = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県",
        "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
        "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
        "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
        "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]


def pref_name(code):
    try:
        i = int(str(code)[:2])
        return PREF[i - 1]
    except Exception:
        return ""


def pref_of_address(addr: str) -> str:
    for p in PREF:
        if str(addr).startswith(p):
            return p
    return ""


def city_of_address(addr: str) -> str:
    """住所から「都道府県＋市区町村」までを取り出す（政令市は区まで）。"""
    a = str(addr).replace(" ", "").replace("　", "")
    p = pref_of_address(a)
    rest = a[len(p):]
    m = re.match(r"(.+?郡.+?[町村])", rest) or re.match(r"(.+?市.+?区)", rest) or \
        re.match(r"(.+?[市区町村])", rest)
    return p + (m.group(1) if m else "")


def trend(rows, key, topn=30, label="", unit="件"):
    """上位 topn 行で key の値がどれに偏っているかを文章にする（ランキングの「傾向」欄）。"""
    from collections import Counter
    top = [r.get(key) for r in rows[:topn] if r.get(key)]
    if not top:
        return ""
    c = Counter(top).most_common(3)
    parts = ["%s %d%s" % (k, v, unit) for k, v in c]
    return "上位%d%sのうち、%s。" % (min(topn, len(rows)), label, "、".join(parts))


def today():
    return _dt.date.today().isoformat()


def write(meta: dict, rankings: list, search: list | None = None, geo: dict | None = None):
    """公開用 JSON を書き出す。最低限の整合性チェックもここで行う。"""
    check(isinstance(rankings, list) and len(rankings) > 0, "ランキングが空です")
    for r in rankings:
        check(r.get("id") and r.get("title") and r.get("columns"), "ランキング定義が不完全: %s" % r.get("id"))
        check(len(r.get("rows", [])) > 0, "ランキング %s の行が0件です" % r["id"])
        for c in r["columns"]:
            if c.get("type") == "num":
                for row in r["rows"][:50]:
                    v = row.get(c["key"])
                    check(v is None or isinstance(v, (int, float)), "数値列 %s に数値以外: %r" % (c["key"], v))
    meta = dict(meta)
    meta.setdefault("status", "ok")
    meta.setdefault("updated", today())
    _dump(OUT / "meta.json", meta)
    _dump(OUT / "rankings.json", rankings)
    if search is not None:
        _dump(OUT / "search.json", search)
    if geo is not None:
        gdir = OUT / "geo"
        gdir.mkdir(exist_ok=True)
        for f in gdir.glob("*.json"):
            f.unlink()
        files = []
        for gid, g in geo.items():
            _dump(gdir / ("%s.json" % gid), {"points": g["points"]})
            files.append({"label": g["label"], "path": "data/geo/%s.json" % gid})
        _dump(gdir / "index.json", {"files": files})
    log("wrote", OUT)


def _dump(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main(fn):
    """fetch.py の入口。DataError なら終了コード2で止める（公開されない）。"""
    try:
        fn()
    except DataError as e:
        print("::error::データ検証で停止しました: %s" % e, file=sys.stderr)
        sys.exit(2)
