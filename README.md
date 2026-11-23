# 有報で見る会社の実態

求人票には書かれない数字が、有価証券報告書には書いてある。平均年収・勤続年数・男女の賃金差・男性の育休取得率を、上場企業などで比べられます。

公開ページ：https://arai-sarai-data.github.io/yuho-jittai/

## 仕組み

- `fetch.py` が公式の公開データを取得・検証・集計し、`docs/data/` に JSON を書き出します。
- GitHub Actions（`.github/workflows/update.yml`）が毎月2日に自動で実行し、GitHub Pages に公開します。
- 元データの形式が想定と違うときは **数字を推測で埋めずに停止** します（前回の正しいデータが表示され続けます）。停止した理由は Actions のログに `データ検証で停止しました` として出ます。

## 最初の設定（1回だけ）

1. このフォルダの中身を `arai-sarai-data/yuho-jittai` リポジトリ（Public）に置く。
2. Settings → Pages → Build and deployment の Source を **GitHub Actions** にする。
3. Settings → Actions → General → Workflow permissions を **Read and write permissions** にする。
3-1. Settings → Secrets and variables → Actions に `EDINET_API_KEY` を登録：EDINET API のキー（https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1 で無料登録）
4. Actions タブ → `update` → **Run workflow** で初回のデータ取得を実行する。

## 出典

- 金融庁のEDINETに提出された有価証券報告書の「従業員の状況」「女性活躍に関する指標」の数字を、会社どうしで比べられるようにしたものです

各データの利用条件に従い、出典を明記して加工・公開しています（`docs/about.html`）。
