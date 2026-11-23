/* 共通フロントエンド。site.json と data/*.json を読んで描画するだけ。
   データの数字はすべて data/ 配下（自動取得スクリプトの出力）から来る。 */
(function () {
  "use strict";
  var S = {}, META = {}, RANKS = [], LANG = "ja";
  var $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function T(obj, key) { // 多言語フィールド: key_en があれば英語時に使う
    if (LANG === "en" && obj[key + "_en"] != null) return obj[key + "_en"];
    return obj[key];
  }
  function fmt(v, f) {
    if (v == null || v === "" || (typeof v === "number" && isNaN(v))) return "—";
    if (typeof v !== "number") return esc(v);
    var loc = LANG === "en" ? "en-US" : "ja-JP";
    if (f === "pct") return (v * 100).toLocaleString(loc, { maximumFractionDigits: 1 }) + "%";
    if (f === "pct100") return v.toLocaleString(loc, { maximumFractionDigits: 1 }) + "%";
    if (f === "1") return v.toLocaleString(loc, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    if (f === "2") return v.toLocaleString(loc, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return Math.round(v).toLocaleString(loc);
  }
  function getJSON(p) {
    return fetch(p, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(p + " " + r.status);
      return r.json();
    });
  }
  function ui(key, ja) { // 画面の固定文言
    var d = (S.ui && S.ui[LANG]) || {};
    return d[key] || ja;
  }

  function applyStatic() {
    document.documentElement.lang = LANG;
    document.documentElement.style.setProperty("--c", S.color || "#d6336c");
    document.title = T(S, "title");
    var md = document.querySelector('meta[name="description"]');
    if (md) md.setAttribute("content", T(S, "tagline"));
    $("brand").textContent = T(S, "short") || T(S, "title");
    $("title").textContent = T(S, "title");
    $("tagline").textContent = T(S, "tagline");
    var staticT = {
      nav_rank: ["ランキング", "Rankings"], nav_map: ["地図", "Map"], nav_search: ["検索", "Search"],
      nav_about: ["出典・注意", "Sources"], h_search: ["さがす", "Search"], h_map: ["地図", "Map"],
      h_rank: ["ランキング", "Rankings"], f_about: ["出典・計算方法・免責・訂正のお願い", "Sources, methods, disclaimer, corrections"]
    };
    document.querySelectorAll("[data-t]").forEach(function (el) {
      var k = el.getAttribute("data-t");
      if (staticT[k]) el.textContent = staticT[k][LANG === "en" ? 1 : 0];
    });
    $("footsrc").textContent = (LANG === "en" ? "Sources: " : "出典：") +
      (META.sources || S.sources || []).map(function (s) { return s.name; }).join(" / ");
    if ((S.langs || []).indexOf("en") >= 0) {
      $("langbtn").hidden = false;
      $("langbtn").textContent = LANG === "en" ? "日本語" : "EN";
    }
  }

  function renderStats() {
    var box = $("stats"); box.innerHTML = "";
    (META.stats || []).forEach(function (s) {
      var d = document.createElement("div"); d.className = "stat";
      d.innerHTML = "<b>" + fmt(s.value, s.fmt) + (s.unit ? "<small>" + esc(T(s, "unit")) + "</small>" : "") +
        "</b><span>" + esc(T(s, "label")) + "</span>";
      box.appendChild(d);
    });
    if (META.updated) {
      $("updated").textContent = (LANG === "en" ? "Data updated: " : "データ更新：") + META.updated +
        (META.data_period ? (LANG === "en" ? " / Period: " : "　対象期間：") + META.data_period : "");
    }
  }

  // ---------- ランキング ----------
  var current = 0;
  function renderTabs() {
    var tabs = $("tabs"); tabs.innerHTML = "";
    RANKS.forEach(function (r, i) {
      var b = document.createElement("button");
      b.textContent = T(r, "tab") || T(r, "title");
      if (i === current) b.className = "on";
      b.onclick = function () { current = i; renderTabs(); renderRank(); history.replaceState(null, "", "#r=" + r.id); };
      tabs.appendChild(b);
    });
  }
  function renderRank() {
    var r = RANKS[current]; if (!r) return;
    var limit = 30, sortKey = null, sortDir = -1;
    var box = $("ranking");
    function draw() {
      var rows = r.rows.slice();
      if (sortKey) rows.sort(function (a, b) {
        var x = a[sortKey], y = b[sortKey];
        if (typeof x === "number" && typeof y === "number") return (x - y) * sortDir;
        return String(x).localeCompare(String(y), "ja") * sortDir;
      });
      var barCol = (r.columns.filter(function (c) { return c.bar; })[0] || {}).key;
      var maxv = 0;
      if (barCol) rows.forEach(function (x) { if (typeof x[barCol] === "number") maxv = Math.max(maxv, x[barCol]); });
      var h = '<div class="rk"><h3>' + esc(T(r, "title")) + "</h3>";
      if (T(r, "desc")) h += '<p class="desc">' + esc(T(r, "desc")) + "</p>";
      if (T(r, "trend")) h += '<div class="trend"><b>' + (LANG === "en" ? "Pattern: " : "傾向：") + "</b>" + esc(T(r, "trend")) + "</div>";
      h += '<div class="tw"><table><thead><tr><th class="no">#</th>';
      r.columns.forEach(function (c) {
        h += '<th data-k="' + esc(c.key) + '" class="' + (c.type === "num" ? "n" : "") + '">' + esc(T(c, "label")) + "</th>";
      });
      h += "</tr></thead><tbody>";
      rows.slice(0, limit).forEach(function (row, i) {
        h += '<tr class="' + (i < 3 && !sortKey ? "top3" : "") + '"><td class="no">' + (i + 1) + "</td>";
        r.columns.forEach(function (c) {
          var v = row[c.key];
          if (c.type === "num") {
            var bar = (c.key === barCol && maxv > 0 && typeof v === "number") ?
              '<span class="bar" style="width:' + Math.max(2, Math.round(60 * v / maxv)) + 'px"></span>' : "";
            h += '<td class="n">' + fmt(v, c.fmt) + bar + "</td>";
          } else if (c.type === "link") {
            var u = row[c.key + "_url"];
            h += "<td>" + (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(v) + "</a>" : esc(v)) + "</td>";
          } else h += "<td>" + esc(v) + "</td>";
        });
        h += "</tr>";
      });
      h += "</tbody></table></div>";
      h += '<div class="rkfoot"><span>' + (LANG === "en" ? "Showing " : "表示 ") + Math.min(limit, rows.length) + " / " + rows.length + "</span>";
      if (rows.length > limit) h += '<button class="more">' + (LANG === "en" ? "Show more" : "もっと見る") + "</button>";
      h += '<button class="share">' + (LANG === "en" ? "Share on X" : "Xでシェア") + "</button></div>";
      if (T(r, "method")) h += '<details class="method"><summary>' + (LANG === "en" ? "How this is calculated" : "計算方法と注意") + "</summary><p>" + esc(T(r, "method")) + "</p></details>";
      h += "</div>";
      box.innerHTML = h;
      box.querySelectorAll("th[data-k]").forEach(function (th) {
        th.onclick = function () {
          var k = th.getAttribute("data-k");
          if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; }
          draw();
        };
      });
      var m = box.querySelector(".more"); if (m) m.onclick = function () { limit += 50; draw(); };
      box.querySelector(".share").onclick = function () { share(r); };
    }
    draw();
  }
  function share(r) {
    var label = r.share_label || (r.columns[0] && r.columns[0].key);
    var val = r.share_value;
    var col = r.columns.filter(function (c) { return c.key === val; })[0];
    var top = r.rows.slice(0, 3).map(function (x, i) {
      return (i + 1) + "位 " + x[label] + (col ? "（" + fmt(x[val], col.fmt).replace(/<[^>]+>/g, "") + (col.unit || "") + "）" : "");
    }).join("\n");
    if (LANG === "en") top = top.replace(/(\d)位/g, "#$1");
    var text = "【" + T(r, "title") + "】\n" + top + "\n";
    var url = location.origin + location.pathname + "#r=" + r.id;
    var tags = (S.hashtags || []).join(",");
    window.open("https://x.com/intent/post?text=" + encodeURIComponent(text) +
      "&url=" + encodeURIComponent(url) + (tags ? "&hashtags=" + encodeURIComponent(tags) : ""), "_blank", "noopener");
  }

  // ---------- 検索 ----------
  var SEARCH = null;
  function initSearch() {
    if (!S.search) return;
    $("search").hidden = false; $("navsearch").hidden = false;
    $("q").placeholder = T(S.search, "placeholder") || "";
    var timer = null;
    $("q").oninput = function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var q = $("q").value.trim();
        if (!q) { $("results").innerHTML = ""; return; }
        var go = function () { doSearch(q); };
        if (SEARCH) go();
        else getJSON("data/search.json").then(function (d) { SEARCH = d; go(); })
          .catch(function () { $("results").textContent = ui("nodata", "データ準備中です"); });
      }, 200);
    };
  }
  function norm(s) { return String(s).toLowerCase().replace(/[\s　]/g, "").replace(/[Ａ-Ｚａ-ｚ０-９]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0xFEE0); }); }
  function doSearch(q) {
    var nq = norm(q), out = [];
    for (var i = 0; i < SEARCH.length && out.length < 50; i++) {
      var x = SEARCH[i];
      if (norm(x.n + " " + (x.s || "") + " " + (x.a || "")).indexOf(nq) >= 0) out.push(x);
    }
    var h = out.length ? "" : "<p>" + (LANG === "en" ? "No results" : "見つかりませんでした") + "</p>";
    out.forEach(function (x) {
      h += '<div class="hit"><b>' + esc(x.n) + "</b>" + (x.s ? " <span class=\"kv\">" + esc(x.s) + "</span>" : "") +
        '<div class="kv">' + (x.k || []).map(function (kv) { return esc(kv[0]) + "：" + esc(kv[1]); }).join("　") + "</div>" +
        (x.u ? '<a href="' + esc(x.u) + '" target="_blank" rel="noopener">' + (LANG === "en" ? "Original record" : "原本を見る") + "</a>" : "") + "</div>";
    });
    $("results").innerHTML = h;
  }

  // ---------- 地図 ----------
  var MAP = null, LAYER = null;
  function initMap() {
    if (!S.map || typeof L === "undefined") return;
    getJSON("data/geo/index.json").then(function (gi) {
      $("map").hidden = false; $("navmap").hidden = false;
      $("mapnote").textContent = T(S.map, "note") || "";
      MAP = L.map("leaflet", { preferCanvas: true }).setView(S.map.center || [36.2, 138.2], S.map.zoom || 5);
      L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
        maxZoom: 18, attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>'
      }).addTo(MAP);
      var sel = document.createElement("select");
      gi.files.forEach(function (f) {
        var o = document.createElement("option"); o.value = f.path; o.textContent = f.label; sel.appendChild(o);
      });
      sel.onchange = function () { loadGeo(sel.value); };
      $("mapctl").appendChild(sel);
      if (gi.files.length) loadGeo(gi.files[0].path);
    }).catch(function () { /* 地図データなし */ });
  }
  function loadGeo(path) {
    getJSON(path).then(function (g) {
      if (LAYER) MAP.removeLayer(LAYER);
      LAYER = L.layerGroup();
      var maxv = 0; g.points.forEach(function (p) { maxv = Math.max(maxv, p[2]); });
      var bounds = [];
      g.points.forEach(function (p) {
        var r = 4 + 14 * Math.sqrt(p[2] / (maxv || 1));
        var m = L.circleMarker([p[0], p[1]], { radius: r, color: S.color, weight: 1, fillColor: S.color, fillOpacity: 0.45 });
        m.bindPopup("<b>" + esc(p[3]) + "</b><br>" + esc(p[4] || "").replace(/\n/g, "<br>"));
        LAYER.addLayer(m); bounds.push([p[0], p[1]]);
      });
      LAYER.addTo(MAP);
      if (bounds.length) MAP.fitBounds(bounds, { padding: [20, 20], maxZoom: 14 });
    });
  }

  // ---------- 起動 ----------
  function boot() {
    var qs = new URLSearchParams(location.search);
    getJSON("site.json").then(function (site) {
      S = site;
      LANG = qs.get("lang") || ((S.langs || [])[0]) || "ja";
      if ((S.langs || []).indexOf("en") >= 0) {
        $("langbtn").onclick = function () {
          qs.set("lang", LANG === "en" ? "ja" : "en"); location.search = qs.toString();
        };
      }
      return Promise.all([
        getJSON("data/meta.json").catch(function () { return null; }),
        getJSON("data/rankings.json").catch(function () { return []; })
      ]);
    }).then(function (res) {
      META = res[0] || {}; RANKS = res[1] || [];
      applyStatic();
      if (!res[0] || META.status !== "ok") {
        $("status").hidden = false;
        $("status").textContent = LANG === "en" ?
          "Data is being prepared. It is fetched automatically from the official sources." :
          "データ準備中です。公式の公開データを自動で取得してから表示します。";
      }
      renderStats();
      var m = location.hash.match(/r=([\w-]+)/);
      if (m) RANKS.forEach(function (r, i) { if (r.id === m[1]) current = i; });
      if (RANKS.length) { renderTabs(); renderRank(); } else $("rank").hidden = true;
      initSearch(); initMap();
    }).catch(function (e) {
      $("status").hidden = false; $("status").textContent = "読み込みに失敗しました：" + e.message;
    });
  }
  boot();
})();
