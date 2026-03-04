# Bot コンテナ化の必要性と Azure デプロイ先比較

## Bot がコンテナである必要性

このプロジェクトの「Bot」は、ブラウザ（Playwright + Chromium）経由で Google Meet / Teams / Zoom に参加し、仮想オーディオでリアルタイム文字起こしを行うプログラムである。以下の理由からコンテナ化が必須となる。

| 理由 | 詳細 |
|------|------|
| **複雑なシステム依存** | Xvfb（仮想ディスプレイ）、PulseAudio（仮想オーディオ）、Chromium、FFmpeg など、OS レベルのパッケージが多数必要 |
| **環境の再現性** | PulseAudio の設定、ALSA→PulseAudio ルーティング、仮想デバイスの構成など、ホスト環境に依存するセットアップをイメージに固定できる |
| **API サーバーとの分離** | Bot は CPU/メモリを大量消費する（Chromium + 音声処理）。API サーバーのリソースを圧迫しないよう隔離が必要 |
| **並行実行** | 複数会議に同時参加するため、Bot ごとに独立したプロセス空間（Display 番号、PulseAudio ソケット）が必要 |
| **セキュリティ** | 非 root ユーザー（`botuser`）でのブラウザ実行、録音ファイルの隔離 |

Git 履歴（`bf3ea7a`）で一度 **App Service subprocess 方式**を試みたが、`apt-get install` に 2〜3 分かかる問題や、App Service 再起動時に毎回依存パッケージの再インストールが必要になる問題が発生し、最終的にコンテナ方式（ACA Job）に移行している（`a6b2d21`）。

---

## デプロイ先候補の比較一覧

### 前提条件（本プロジェクト固有）

- Bot イメージは **ACR**（`acr002tech0nottadev.azurecr.io`）に格納
- Bot は **オンデマンド起動**（API 呼び出しで会議参加 → 終了後自動停止）
- 1 回の実行は **30 分〜2 時間**程度（会議の長さに依存）
- リソース要件: **CPU 1 コア / メモリ 2GB**（Chromium + 音声処理）
- API サーバーは別途 Azure App Service で稼働中

### 比較表

| 観点 | **ACR (単体)** | **ACI** | **App Service subprocess** | **ACA Job** | **ACA App (minReplicas=1)** | **App Service (Web App for Containers)** | **AKS** |
|------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **概要** | コンテナレジストリ（保管のみ） | サーバーレスコンテナ実行 | API サーバー内でプロセス起動 | サーバーレスコンテナジョブ | 常時ウォームコンテナ | コンテナを App Service で常時稼働 | Kubernetes クラスター |
| **会議参加までの時間** | N/A | 60〜90 秒 | **1〜3 秒** | **25〜35 秒**（最適化後） | **2〜5 秒** | 常時起動なら即座 / コールドスタート 30〜60 秒 | ウォームなら数秒 / コールドなら 30〜60 秒 |
| **運用コスト (月額目安)** | イメージ保管のみ ¥500〜 | 実行時間課金 **¥2,000〜5,000** | **¥0**（追加コストなし） | 実行時間課金 **¥1,500〜4,000** | 常時1台 **¥2,000〜4,000** | 常時起動 **¥5,000〜15,000** | **¥15,000〜50,000+** |
| **技術的難易度** | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★★★★ |
| **オンデマンド起動** | N/A | 対応 | 対応（即座） | **対応（Job execution で最適化）** | 対応（常時ウォーム） | 非対応（常時起動前提） | 対応（Pod スケールアウト） |
| **自動停止** | N/A | コンテナ終了で自動 | プロセス終了で自動 | **Job execution 完了で自動停止** | コンテナ常駐（停止しない） | 非対応（手動停止しない限り課金） | Pod termination で自動 |
| **スケーラビリティ** | N/A | 同時に複数コンテナ作成可能 | App Service の CPU/メモリに制約 | **並列 execution 数で柔軟に制御** | スケールルールで自動調整 | インスタンス追加でスケール | 高い（ノード自動スケール） |
| **API サーバーへの影響** | なし | なし | **大きい**（CPU/メモリ共有） | なし | なし | なし | なし |
| **依存パッケージ管理** | イメージに固定 | イメージに固定 | **毎回 apt-get が必要（2〜3 分）** | イメージに固定 | イメージに固定 | イメージに固定 | イメージに固定 |
| **ログ・監視** | N/A | Azure Monitor（制限あり） | App Service ログに混在 | **Azure Monitor + Log Analytics** | Azure Monitor + Log Analytics | App Service ログ | Azure Monitor + Prometheus |
| **Secret 管理** | N/A | 環境変数のみ | App Service の環境変数 | **ACA Secret + secret_ref** | ACA Secret + secret_ref | App Service の環境変数 | Kubernetes Secret / Key Vault |
| **CI/CD 連携** | GitHub Actions で push | SDK/CLI で起動 | デプロイ不要 | **GitHub Actions → ACR → Job start** | GitHub Actions → ACR → App update | GitHub Actions → ACR | Helm / ArgoCD / GitHub Actions |
| **プロジェクトでの実績** | 現在使用中（イメージ保管） | `076d186` で採用 → 遅延問題で移行 | `bf3ea7a` で採用 → 依存管理問題で移行 | **`a6b2d21` で採用（現在の方式）** | 未採用（将来の短縮候補） | 未採用 | 未採用 |

---

## 各方式の詳細評価

### 1. ACR（Azure Container Registry）-- イメージ保管のみ

- **役割**: 実行基盤ではなく、Bot イメージの保管庫
- **現状**: `acr002tech0nottadev.azurecr.io/tech0notta-bot` として使用中
- **結論**: どの実行基盤を選んでも ACR は必要。比較対象外

### 2. ACI（Azure Container Instances）-- 初期採用 → 廃止

- **採用時期**: `076d186` (2026-03-01)
- **廃止理由**: コールドスタートに **60〜90 秒**かかり、ユーザーが会議参加を待てなかった
- **長所**: シンプルな API、実行時間のみ課金
- **短所**: コールドスタート遅延、コンテナグループ管理の柔軟性が低い

### 3. App Service subprocess -- 2 回目の試行 → 廃止

- **採用時期**: `bf3ea7a` (2026-03-03)
- **コミットメッセージ**: _「ACI → App Service subprocess 方式に変更（会議参加高速化）」_
- **狙い**: コンテナ起動を省略し **1〜3 秒**で会議参加
- **廃止理由**（後続コミット群で判明）:
  - `startup.sh` で `apt-get install` に **230 秒タイムアウト**が発生（`e101ad7`）
  - Xvfb ロックファイル競合、PulseAudio ソケット不整合（`21911be`, `660c45b`）
  - App Service 再起動のたびに Playwright/Chromium を再インストール
  - Bot の CPU/メモリ消費が API サーバーを圧迫

### 4. ACA Job（Azure Container Apps）-- 現在の方式

- **採用時期**: `a6b2d21` (2026-03-04)
- **コミットメッセージ**: _「Replace the subprocess-based bot execution model with Azure Container Apps (ACA) Job execution」_
- **長所**:
  - 依存パッケージがイメージにベイク済み（apt-get 不要）
  - API サーバーと完全分離
  - `secret_ref` で `AZURE_SPEECH_KEY` を安全に渡せる
  - Job execution 完了で自動停止（課金停止）
- **現在の構成**: `bot_service.py` → `ContainerAppsAPIClient` → `jobs.begin_start()`
- **実績**: Google Meet / Teams / Zoom の 3 プラットフォームで会議参加を確認済み
- **最適化済み** (`0967a8c`):
  - Chromium 起動フラグ 11 個追加（GPU/拡張機能無効化など）
  - Xvfb + PulseAudio 並列起動、xdpyinfo による準備完了チェック
  - 各 Bot の不要な sleep / タイムアウトを短縮
  - ManagedIdentityCredential による ACA SDK トークン取得高速化
  - 起動時の `warmup()` でクライアント事前初期化

### 5. ACA App (minReplicas=1) -- 未採用（将来の短縮候補）

- **概要**: ACA Job ではなく ACA App として常時 1 台のコンテナを起動状態で待機させる
- **会議参加時間**: **2〜5 秒**（コンテナ起動・イメージプルが不要）
- **コスト**: ~¥2,000〜4,000/月（vCPU 1.0 + メモリ 2GiB の常時課金）
- **仕組み**: HTTP エンドポイントで会議 URL を受信 → 即座にブラウザ起動
- **長所**: コールドスタート完全排除、ACA Job と同じインフラ
- **短所**: 会議がなくても常時課金、1 コンテナ = 1 会議の制約（同時会議にはスケールルールが必要）
- **検討理由**: 現在の ACA Job 方式で 25〜35 秒かかる主因はコンテナ起動 + イメージプル。これを排除できる唯一の方法

### 6. App Service (Web App for Containers) -- 未採用

- **概要**: Docker イメージを App Service 上で常時稼働
- **不採用理由**:
  - Bot はオンデマンド実行であり、常時起動は過剰
  - 会議がない時間帯も課金が続く（コスト非効率）
  - 1 インスタンス = 1 Bot の制約で、同時複数会議に対応しにくい

### 7. AKS（Azure Kubernetes Service）-- 未採用

- **概要**: フルマネージド Kubernetes クラスター
- **不採用理由**:
  - MVP フェーズのプロジェクトに対してオーバースペック
  - クラスター管理・ネットワーク設計・RBAC 設定など運用負荷が非常に高い
  - 最低でもノード 1 台の常時稼働コストが発生
  - ACA が Kubernetes の上位抽象として同等機能を提供

---

## 会議参加時間の内訳と最適化

### 現在の時間内訳（ACA Job 方式、最適化済み）

| フェーズ | 所要時間 | 内容 |
|---------|---------|------|
| ACA SDK トークン取得 | ~1 秒 | ManagedIdentityCredential（warmup 済み） |
| ACA Job execution 開始 | ~3〜5 秒 | Azure API 呼び出し |
| コンテナ起動 + イメージプル | ~10〜15 秒 | ACR からイメージ取得 + コンテナ初期化 |
| Xvfb + PulseAudio 起動 | ~1 秒 | 並列起動 + xdpyinfo チェック |
| Chromium 起動 | ~3〜5 秒 | 11 個の高速化フラグ適用 |
| ページ読み込み + 会議参加操作 | ~5〜10 秒 | プラットフォーム固有の操作 |
| **合計** | **~25〜35 秒** | |

### 実施済みの最適化（`0967a8c`）

| カテゴリ | 施策 | 効果 |
|---------|------|------|
| **Chromium** | `--disable-gpu`, `--disable-extensions`, `--disable-dev-shm-usage` 等 11 フラグ | 起動 ~2 秒短縮 |
| **エントリポイント** | Xvfb + PulseAudio 並列起動、xdpyinfo readiness チェック | ~1〜2 秒短縮 |
| **Bot 操作** | 不要な sleep 削除、タイムアウト短縮（10s→5s 等） | ~4〜5 秒短縮 |
| **ページ読み込み** | `networkidle` → `domcontentloaded` | ~2〜3 秒短縮 |
| **ACA SDK** | ManagedIdentityCredential + startup warmup | ~3〜5 秒短縮 |
| **合計** | | **~15〜20 秒短縮** |

### さらなる短縮の選択肢

#### Tier 1: クイックウィン（追加コスト $0）

| 施策 | 予想効果 | 難易度 | 内容 |
|------|---------|--------|------|
| **Docker イメージ軽量化** | イメージプル ~3〜5 秒短縮 | ★★☆☆☆ | 不要パッケージ削除、マルチステージビルド。現在のイメージは ~1.5GB と見込まれ、800MB 以下に削減可能 |
| **Chromium headless=new** | 起動 ~1〜2 秒短縮 | ★☆☆☆☆ | 新しいヘッドレスモード。ただし Google Meet / Teams の動作検証が必要 |
| **ACR Artifact Streaming** | イメージプル ~3〜5 秒短縮 | ★★☆☆☆ | イメージを完全にプルする前にコンテナ起動を開始。ACR Premium SKU が必要な場合あり |

#### Tier 2: インフラ変更（月額 ~¥2,000〜4,000）

| 施策 | 予想効果 | 難易度 | 内容 |
|------|---------|--------|------|
| **ACA App (minReplicas=1)** | **~20〜25 秒短縮**（参加 2〜5 秒に） | ★★★☆☆ | 常時 1 台のウォームコンテナを維持。コンテナ起動・イメージプルを完全排除。HTTP で会議 URL を受信して即座にブラウザ起動。同時会議にはスケールルールで追加コンテナを起動 |
| **プリウォームBot Pool** | **~20〜25 秒短縮** | ★★★★☆ | 事前に Xvfb + Chromium 起動済みのコンテナをプール。WebSocket や HTTP long-polling で会議指示を待機 |

#### 効果まとめ

| 組み合わせ | 参加時間 | 追加コスト |
|-----------|---------|-----------|
| 現状（最適化済み ACA Job） | 25〜35 秒 | $0 |
| + Tier 1 全部 | 15〜25 秒 | $0 |
| + Tier 2 (ACA App) | **2〜5 秒** | ~¥2,000〜4,000/月 |

---

## 方式変遷のタイムライン（Git 履歴ベース）

```
2026-03-01  076d186  feat: migrate bot runner from Docker to ACI
                     └─ 最初の方式。ACI でコンテナ起動。コールドスタート 60〜90 秒が問題に

2026-03-03  bf3ea7a  feat(bot): ACI → App Service subprocess 方式に変更
                     └─ 高速化のため subprocess 方式へ。1〜3 秒で会議参加可能に

2026-03-03  e101ad7  Optimize startup.sh: run apt-get in background to avoid 230s timeout
  〜        e63e7a9  (10+ fix commits)
2026-03-03  660c45b  └─ apt-get 遅延、Xvfb/PulseAudio 競合など多数の問題が発生

2026-03-04  a6b2d21  feat: migrate bot execution from App Service subprocess to ACA Job
                     └─ ACA Job 方式に移行。依存はイメージにベイク、API と分離

2026-03-04  f4cef4d  fix: correct ACA SDK package name and use EnvironmentVar model
                     └─ SDK の微調整

2026-03-04  c6e826b  fix: bypass Cloudflare bot detection on Zoom web client
                     └─ Zoom の Cloudflare チャレンジ対策（ステルススクリプト + URL変換）

2026-03-04  59579fb  fix: fix Zoom bot name input selector and join button click
                     └─ Zoom セレクタ修正（input#input-for-name, JS click でオーバーレイ回避）

2026-03-04  bc652ac  fix: sync bot status with actual meeting join timing
                     └─ ステータス遷移修正（JOINING → IN_MEETING は /joining コールバックで）

2026-03-04  a4be3af  fix: unify all timestamps to JST (Asia/Tokyo)
                     └─ 全タイムスタンプを日本標準時に統一

2026-03-04  0967a8c  perf: optimize bot join time (~15-20s reduction)
                     └─ Chromium フラグ、並列起動、sleep 削減、SDK warmup（現在の最新）
```

---

## 結論

| 方式 | 総合評価 | 理由 |
|------|:--------:|------|
| **ACA Job** | **最適（採用中）** | オンデマンド課金 + イメージ固定 + API 分離 + Secret 管理。参加 25〜35 秒。MVP〜本番まで対応可能 |
| ACA App (minReplicas=1) | **次のステップ候補** | 参加 2〜5 秒。月額 ~¥3,000 で劇的な UX 改善。ACA Job と同じインフラで移行容易 |
| ACI | 参考 | シンプルだがコールドスタートの制御が難しい |
| App Service subprocess | 不適 | 高速だが依存管理・リソース競合が深刻 |
| App Service (Containers) | 不適 | 常時起動コストがオンデマンド用途に合わない |
| AKS | 過剰 | MVP には運用負荷・コストともにオーバースペック |

現在の **ACR（イメージ保管）+ ACA Job（オンデマンド実行）** の組み合わせは、このプロジェクトの要件（オンデマンド起動、複雑な依存、API 分離、コスト効率）に最も適合した選択である。さらなる UX 改善が必要な場合は、**ACA App (minReplicas=1)** への移行が最も費用対効果の高い次のステップとなる。
