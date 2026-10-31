# Math Curve 2 — 最初に読む

**編集する最新版は `01_編集用/math_curve_2` です。**

基準リリースは **26.2.0 / hotfix1**（既存ZIPの作成日: 2026-08-12）。
2026-10-31にフォルダーを整理しました。今回、新しい製品リリースは作成していません。

## 編集を始める

[最新版の編集用フォルダー](01_編集用/math_curve_2) を開いてください。
VS Codeを使う場合は、ルートにある **`Math_Curve_2.code-workspace`** を開くと、このフォルダーが直接開きます。

- 主な処理: [math_curve_2.py](01_編集用/math_curve_2/math_curve_2.py)
- ライセンス処理: [license_manager.py](01_編集用/math_curve_2/license_manager.py)
- 設定: [config.py](01_編集用/math_curve_2/config.py)
- バージョン・対応OS: [math_curve_2.manifest](01_編集用/math_curve_2/math_curve_2.manifest)
- 変更履歴: [IMPROVEMENTS.md](01_編集用/math_curve_2/IMPROVEMENTS.md)
- Marketplace提出資料: [MarketplaceSubmission](01_編集用/math_curve_2/MarketplaceSubmission)

アドインの構成、Git履歴、既存の未コミット変更、テスト、エディター設定は編集用フォルダーに引き継いでいます。
コード・文書を変更したら、既存の開発ルールに従って `IMPROVEMENTS.md` に目的と内容を記録してください。

## フォルダーの役割

```text
fusion-addins/
├─ README_最初に読む.md                 この案内
├─ Math_Curve_2.code-workspace          VS Codeで編集を始める入口
├─ 01_編集用/
│  └─ math_curve_2/                    最新版の編集元。今後はここを編集
├─ 02_配布用/
│  └─ 26.2.0_hotfix1/                  現在の基準リリースのZIP 2本
│     ├─ Math_Curve_2_26.2.0_Windows_hotfix1.zip
│     ├─ Math_Curve_2_26.2.0_macOS_hotfix1.zip
│     └─ RELEASE.json                 バージョン、配置、ZIPのSHA-256
└─ 99_アーカイブ/
   ├─ 旧配布ZIP/                       過去版と重複ZIP
   ├─ 展開済み/                        以前ZIPを展開した作業コピー
   ├─ 開発時の生成ファイル/             Pythonキャッシュと書き込み権限テスト
   └─ 整理記録/2026-10-31/             整理前一覧、移動記録、検証結果
```

`02_配布用` は配布時点の保存物、`99_アーカイブ` は過去資料です。
編集元を複数に増やさず、日常の変更は `01_編集用/math_curve_2` に集約します。

## 現在の配布一式

| 対象 | 既存の最新ZIP |
| --- | --- |
| Windows | [26.2.0 hotfix1](02_配布用/26.2.0_hotfix1/Math_Curve_2_26.2.0_Windows_hotfix1.zip) |
| macOS | [26.2.0 hotfix1](02_配布用/26.2.0_hotfix1/Math_Curve_2_26.2.0_macOS_hotfix1.zip) |

整理前の編集元は、Windows hotfix1 ZIPの配布対象ファイルとすべて一致していました。
Windows/macOS ZIPの違いは `README.md` と manifest の対応OSです。
macOSの提出前確認事項は、既存の [MACOS_SUBMISSION_NOTES.md](01_編集用/math_curve_2/MarketplaceSubmission/MACOS_SUBMISSION_NOTES.md) を参照してください。
この整理で動作コード・素材・既存ZIPの内容は変更していません。

## 変更した後の扱い

編集用ソースの変更は、保存済みZIPに自動では反映されません。
変更後はFusionで動作確認し、配布する際は新しいバージョンまたは修正番号のフォルダーを `02_配布用` に作成して、一式を保存してください。
その際に、この案内と `RELEASE.json` も更新します。

Fusionに編集元を登録するときは `01_編集用/math_curve_2` を選びます。
今回、Fusion側のアドイン登録設定は変更していません。

## 過去版と整理記録

旧ZIP 11本、展開済みフォルダー2つ、生成ファイルは削除せず `99_アーカイブ` にまとめました。
ファイルごとの元の場所・サイズ・SHA-256は [整理前ファイル一覧.json](99_アーカイブ/整理記録/2026-10-31/整理前ファイル一覧.json)、移動先は [移動記録.json](99_アーカイブ/整理記録/2026-10-31/移動記録.json) に記録しています。
変更した既存文書の原本も、整理記録内の `編集前文書` に保存しています。
