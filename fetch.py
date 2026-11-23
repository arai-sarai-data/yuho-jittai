"""有報で見る会社の実態：EDINET API（金融庁）で直近1年に提出された有価証券報告書から、
提出会社（単体）の平均年収・平均勤続年数・平均年齢・従業員数と、
女性管理職比率・男性の育休取得率・男女の賃金の差異を取り出して比べる。

必要：EDINET API のキー（無料登録）を GitHub の Secrets に EDINET_API_KEY として登録。"""
import csv
import datetime as dt
import io
import os
from collections import defaultdict

from lib import oc

API = "https://api.edinet-fsa.go.jp/api/v2"
CODELIST = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
KEY = os.environ.get("EDINET_API_KEY", "")
DAYS = int(os.environ.get("YUHO_DAYS", "380"))

# 項目名（日本語ラベル）に含まれる語 → 項目（要素IDで見つからないときに使う）
LABELS = {
    "salary": [["平均年間給与"]],
    "tenure": [["平均勤続年数"]],
    "age": [["平均年齢"]],
    "emp": [["従業員数"]],
    "fmgr": [["管理職に占める女性労働者の割合"]],
    "mleave": [["男性", "育児休業取得率"], ["男性労働者の育児休業取得率"]],
    "gap": [["男女の賃金の差異", "全労働者"]],
}
# 要素IDに含まれる語 → 項目
ITEMS = {
    "salary": ["AverageAnnualSalaryInformationAboutReportingCompany"],
    "tenure": ["AverageLengthOfServiceYearsInformationAboutReportingCompany"],
    "age": ["AverageAgeYearsInformationAboutReportingCompany"],
    "emp": ["NumberOfEmployees"],
    "fmgr": ["RatioOfFemaleEmployeesInManagerialPositions"],
    "mleave": ["RatioOfMaleEmployeesTakingParentalLeave", "RatioOfMaleEmployeesTakingChildcareLeave"],
    "gap": ["DifferenceInWagesBetweenMaleAndFemaleEmployeesAllEmployees"],
}


def industries():
    files = oc.unzip(oc.get(CODELIST, timeout=300))
    b = next(v for k, v in files.items() if k.lower().endswith(".csv"))
    rows = list(csv.reader(io.StringIO(oc.decode(b))))
    hdr_i = next(i for i, r in enumerate(rows[:5]) if any("ＥＤＩＮＥＴコード" in c or "EDINETコード" in c for c in r))
    hdr = rows[hdr_i]
    ic = next(i for i, h in enumerate(hdr) if "ＥＤＩＮＥＴコード" in h or "EDINETコード" in h)
    ii = next(i for i, h in enumerate(hdr) if "業種" in h)
    return {r[ic]: r[ii] for r in rows[hdr_i + 1:] if len(r) > ii}


def doc_list():
    docs = {}
    d = dt.date.today()
    for i in range(DAYS):
        day = (d - dt.timedelta(days=i)).isoformat()
        j = oc.get(API + "/documents.json", params={"date": day, "type": 2, "Subscription-Key": KEY}, as_json=True)
        oc.check(str(j.get("metadata", {}).get("status")) in ("200", ""), "EDINET APIエラー: %s" % j.get("metadata"))
        for x in j.get("results") or []:
            if x.get("docTypeCode") == "120" and x.get("ordinanceCode") == "010" and x.get("csvFlag") == "1" \
                    and x.get("withdrawalStatus") == "0":
                e = x["edinetCode"]
                if e not in docs or x["submitDateTime"] > docs[e]["submitDateTime"]:
                    docs[e] = x
    return docs


def values(doc_id):
    b = oc.get(API + "/documents/" + doc_id, params={"type": 5, "Subscription-Key": KEY}, cache="edinet/%s.zip" % doc_id,
               timeout=300)
    files = oc.unzip(b)
    out = {}
    for name, data in files.items():
        if not name.endswith(".csv") or "jpcrp" not in name:
            continue
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            text = oc.decode(data)
        for r in csv.reader(io.StringIO(text), delimiter="\t"):
            if len(r) < 9:
                continue
            el, label, ctx, val = r[0], r[1], r[2], r[8]
            if not (ctx.startswith("CurrentYear") or ctx.startswith("FilingDate")):
                continue
            for k, pats in ITEMS.items():
                if k in out:
                    continue
                by_el = any(p in el for p in pats)
                by_label = any(all(w in label for w in ws) for ws in LABELS[k]) and "前" not in label
                if by_el or by_label:
                    if k == "emp" and ctx != "CurrentYearInstant_NonConsolidatedMember":
                        continue
                    if k != "emp" and "Member" in ctx.replace("NonConsolidatedMember", ""):
                        continue
                    v = oc.num(val)
                    if v is not None:
                        out[k] = v
    return out


def run():
    oc.check(KEY, "EDINET_API_KEY が設定されていません（Secrets に登録してください）")
    ind = industries()
    docs = doc_list()
    oc.check(len(docs) > 2500, "有価証券報告書が少なすぎます(%d)" % len(docs))
    rows = []
    for n, (e, x) in enumerate(docs.items()):
        try:
            v = values(x["docID"])
        except oc.DataError as err:
            oc.log("skip", e, err)
            continue
        if not v:
            continue
        rows.append({"name": x.get("filerName", ""), "ind": ind.get(e, ""), "period": (x.get("periodEnd") or "")[:7],
                     "url": "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?" + x["docID"], **v})
        if n % 200 == 0:
            oc.log("docs", n, len(docs))
    oc.check(sum(1 for r in rows if "salary" in r) > 2000, "平均年収を読み取れた会社が少なすぎます")
    # 比率は XBRL では小数（0.123 = 12.3%）。1を超える値は%表記とみなして直す。
    for r in rows:
        for k in ("fmgr", "mleave", "gap"):
            if k in r and r[k] > 1.5:
                r[k] = r[k] / 100

    meth = ("EDINETに直近%d日間に提出された有価証券報告書（訂正を除く最新のもの）の「従業員の状況」「女性活躍に関する指標」の値で、"
            "提出会社単体の数字です（グループ全体ではありません）。持株会社は従業員が少なく、平均年収が高く出る傾向があります。"
            "男女の賃金の差異は「男性の賃金に対する女性の賃金の割合」で、100%%に近いほど差が小さいことを示します。"
            "常時雇用する労働者が少ない会社など、開示義務のない項目は空欄です。" % DAYS)
    base_cols = [{"key": "name", "label": "会社", "type": "link"}, {"key": "ind", "label": "業種"}]
    def R(rid, tab, title, key, label, fmt, reverse, desc, minemp=100):
        rr = [dict(r, name_url=r["url"]) for r in rows if key in r and (r.get("emp") or 0) >= minemp]
        rr.sort(key=lambda r: r[key], reverse=reverse)
        return {"id": rid, "tab": tab, "title": title, "desc": desc, "rows": rr,
                "columns": base_cols + [{"key": key, "label": label, "type": "num", "fmt": fmt, "bar": True},
                                        {"key": "emp", "label": "従業員数（単体）", "type": "num"},
                                        {"key": "period", "label": "決算期"}],
                "trend": oc.trend(rr, "ind", 50, "社", "社"), "method": meth, "share_label": "name", "share_value": key}
    out = [
        R("gap", "男女の賃金差", "女性の賃金が男性より低い会社", "gap", "男性を100とした女性の賃金", "pct", False,
          "全労働者の男女の賃金の差異。低いほど女性の賃金が男性より低い。"),
        R("mleave", "男性の育休", "男性の育休取得率が低い会社", "mleave", "男性の育休取得率", "pct", False,
          "有価証券報告書で開示された男性労働者の育児休業取得率。"),
        R("fmgr", "女性管理職", "女性管理職が少ない会社", "fmgr", "女性管理職比率", "pct", False, "管理職に占める女性労働者の割合。"),
        R("tenure", "勤続年数", "平均勤続年数が短い会社", "tenure", "平均勤続年数（年）", "1", False,
          "平均勤続年数が短い順。創業間もない会社や急成長中の会社は短くなります。"),
        R("salary", "平均年収", "平均年間給与が高い会社", "salary", "平均年間給与（円）", "", True, "提出会社の従業員の平均年間給与。"),
    ]
    # 業種ごとの平均（傾向）
    agg = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for k in ("salary", "gap", "mleave", "fmgr", "tenure"):
            if k in r and (r.get("emp") or 0) >= 100:
                agg[r["ind"]][k].append(r[k])
    ir = []
    for k, d in agg.items():
        if not k or len(d.get("salary", [])) < 10:
            continue
        med = lambda a: sorted(a)[len(a) // 2] if a else None
        ir.append({"ind": k, "n": len(d["salary"]), "salary": med(d["salary"]), "gap": med(d.get("gap", [])),
                   "mleave": med(d.get("mleave", [])), "fmgr": med(d.get("fmgr", []))})
    ir.sort(key=lambda r: (r["gap"] if r["gap"] is not None else 9))
    out.append({"id": "ind", "tab": "業種別", "title": "業種ごとの中央値", "desc": "業種ごとに会社の値を並べた真ん中の値（中央値）。",
                "rows": ir, "method": meth, "share_label": "ind", "share_value": "gap",
                "columns": [{"key": "ind", "label": "業種"},
                            {"key": "gap", "label": "女性の賃金(男性=100)", "type": "num", "fmt": "pct", "bar": True},
                            {"key": "mleave", "label": "男性育休", "type": "num", "fmt": "pct"},
                            {"key": "fmgr", "label": "女性管理職", "type": "num", "fmt": "pct"},
                            {"key": "salary", "label": "平均年収", "type": "num"},
                            {"key": "n", "label": "社数", "type": "num"}]})
    pct = lambda v: "—" if v is None else "%.1f%%" % (v * 100)
    search = [{"n": r["name"], "s": r["ind"], "u": r["url"],
               "k": [["平均年収", "%s円" % format(round(r["salary"]), ",") if "salary" in r else "—"],
                     ["勤続", "%.1f年" % r["tenure"] if "tenure" in r else "—"],
                     ["男女賃金", pct(r.get("gap"))], ["男性育休", pct(r.get("mleave"))], ["女性管理職", pct(r.get("fmgr"))]]}
              for r in rows]
    meta = {"data_period": "直近%d日に提出された有価証券報告書" % DAYS,
            "stats": [{"label": "集計した会社", "value": len(rows), "unit": "社"},
                      {"label": "男女の賃金差を開示した会社", "value": sum(1 for r in rows if "gap" in r), "unit": "社"}],
            "sources": [{"name": "EDINET（有価証券報告書）", "org": "金融庁", "url": "https://disclosure2.edinet-fsa.go.jp/",
                         "license": "EDINET API 利用規約に従って取得", "retrieved": oc.today()}]}
    oc.write(meta, out, search=search)


if __name__ == "__main__":
    oc.main(run)
