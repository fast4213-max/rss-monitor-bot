# rss-monitor-bot

ギズモード・ジャパン RSS 監視 & Discord 通知システムこのシステムは、ギズモード・ジャパンの最新記事（RSS）を定期監視し、DiscordのWebhookを介してチャンネルへ自動投稿します。前回の通知済み記事をリポジトリ内の JSON ファイル（state.json）で管理し、重複のない安全な差分通知を行います。🛠️ システム構成[cron-job.org (外部トリガー/cron)]
      │ (POST /repository_dispatch)
      ▼
[GitHub Actions (monitor.yml)]
      │ (Pythonを実行、RSSとstate.jsonを比較)
      ├─► [ギズモードRSS ([https://www.gizmodo.jp/index.xml](https://www.gizmodo.jp/index.xml))]
      │
      ├─► [Discord Webhook (Embed通知)]
      │
      ▼ (新着があれば state.json をコミットして保存)
[GitHub Repository]
⚙️ 導入手順1. Discord Webhook URL の取得通知先のDiscordチャンネル設定（歯車マーク）を開きます。「連携サービス」 ＞ 「ウェブフック」 を選択し、新しいウェブフックを作成します。ウェブフックのURL（https://discord.com/api/webhooks/...）をコピーしておきます。2. GitHub 個人用アクセストークン (PAT) の作成GitHub Actionsに state.json の変更をコミットさせ、さらに cron-job.org からトリガーを引くために、適切な権限を持つアクセストークン（PAT）が必要です。GitHubの右上プロフィール ＞ Settings ＞ Developer settings ＞ Personal access tokens ＞ Tokens (classic) へ進みます。Generate new token (classic) をクリックします。Scope で以下をチェックします：repo （プライベートリポジトリの場合必須。パブリックでもコミットのために必要）トークンを生成し、必ずコピーして控えておきます。3. GitHub Secrets の登録リポジトリの Settings ＞ Secrets and variables ＞ Actions に移動し、New repository secret から以下を登録します。名前値説明DISCORD_WEBHOOK_URLhttps://discord.com/api/...手順1で作成したDiscordのWebhook URLPAT_TOKENghp_xxxxxxxxxxxx手順2で作成したGitHubのPersonal Access Token⏰ 外部トリガーの設定 (cron-job.org)GitHub Actionsの標準機能である schedule は、実行遅延が激しく（数十分〜数時間のズレ）、またリポジトリがアクティブでないと停止する制約があります。そのため、cron-job.org を使用して15分〜30分に1回、確実に起動させます。1. 設定項目Title: Gizmodo RSS TriggerURL: https://api.github.com/repos/{オーナー名}/{リポジトリ名}/dispatchesRequest Method: POSTExecution schedule: Every 15 minutes (15分おきなど、お好みの間隔)2. HTTP Headers (重要)以下のヘッダーを必ず追加してください。User-Agent: cron-job.orgAccept: application/vnd.github+jsonAuthorization: Bearer {あなたのPAT_TOKEN}X-GitHub-Api-Version: 2022-11-283. Request Body (JSON)「Raw data」として以下を指定します。{
  "event_type": "trigger_rss_check"
}
🚨 過去の失敗（403/429エラー）への対策仕様User-Agent の厳格設定:Discord やギズモードのサーバーからロボット判定されて403エラーを喰らうのを防ぐため、Pythonの通信には一般的な Chrome の User-Agent を付与してリクエストを行います。指数バックオフ・レートリミット対策:Discord Webhookに過剰なリクエストが送られた場合、HTTP 429（Too Many Requests）が返されます。このシステムでは、Discordが返す Retry-After（待機秒数）ヘッダーを解析し、その時間分正確に一時停止してから自動再送します。Embed送信の10件安全制限:ギズモードは更新頻度が高いため、長時間の未起動後に起動した際、大量の新規記事が検知される可能性があります。Discord Webhookは1リクエストあたり最大10件までのEmbedしか受け付けません。本スクリプトは差分が15件あっても、最古のものから順番に「最大10件」に厳密に絞り込んでから1回で送信します。これにより、Discord側のペナルティを回避します。
