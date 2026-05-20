#!/usr/bin/env python3
import os
import json
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime

# 設定
RSS_URL = "https://www.gizmodo.jp/index.xml"
STATE_FILE = "state.json"
MAX_EMBEDS = 10  # Discord Webhookの1回あたり最大Embed制限
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def log(message: str, level: str = "INFO"):
    """タイムスタンプ付きのログ出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def fetch_rss_feed(url: str) -> list:
    """RSSフィードを取得して解析する（HTTP 308等のリダイレクト自動追従機能付き）"""
    log(f"RSSフィードの取得を開始: {url}")
    current_url = url
    max_redirects = 3
    xml_data = None

    # HTTP 307/308 等のリダイレクトを安全に追従するループ
    for attempt in range(max_redirects + 1):
        req = urllib.request.Request(current_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                xml_data = response.read()
                if current_url != url:
                    log(f"リダイレクトに成功しました。最終URL: {response.geturl()}")
                break
        except urllib.error.HTTPError as e:
            # 301, 302, 303, 307, 308 リダイレクトを自前で捕捉して追従する
            if e.code in (301, 302, 303, 307, 308) and attempt < max_redirects:
                new_url = e.headers.get("Location")
                if new_url:
                    log(f"HTTP {e.code} (Redirect) を検知しました。転送先URL: {new_url}")
                    current_url = new_url
                    continue
            
            log(f"RSSの取得に失敗しました (HTTP {e.code}): {e.reason}", "ERROR")
            return []
        except Exception as e:
            log(f"RSS取得中に未知のエラーが発生しました: {e}", "ERROR")
            return []

    if not xml_data:
        log("リダイレクト上限に達したか、またはデータが空です。", "ERROR")
        return []

    # RSS XML 解析
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        log(f"XMLのパースに失敗しました: {e}", "ERROR")
        return []

    articles = []
    for item in root.findall(".//item"):
        title = item.find("title")
        link = item.find("link")
        pub_date = item.find("pubDate")
        creator = item.find("{http://purl.org/dc/elements/1.1/}creator")
        description = item.find("description")

        title_text = title.text if title is not None else "無題"
        link_text = link.text.strip() if link is not None else ""
        pub_date_text = pub_date.text if pub_date is not None else ""
        author_text = creator.text if creator is not None else "GIZMODO JAPAN"
        
        desc_text = ""
        if description is not None and description.text:
            desc_text = description.text.split("<")[0][:100] + "..."

        if link_text:
            articles.append({
                "title": title_text,
                "link": link_text,
                "pub_date": pub_date_text,
                "author": author_text,
                "description": desc_text
            })

    log(f"RSSから {len(articles)} 件の記事を解析しました。")
    return articles


def load_state() -> list:
    """既読のURLリストをロードする"""
    if not os.path.exists(STATE_FILE):
        log("過去の履歴ファイル(state.json)が存在しません。新規作成します。")
        return []
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("notified_urls", [])
    except Exception as e:
        log(f"履歴ファイルの読み込みに失敗しました: {e}", "WARNING")
        return []


def save_state(notified_urls: list):
    """既読のURLリストを保存する"""
    keep_urls = notified_urls[-500:]
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"notified_urls": keep_urls, "updated_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
        log("履歴ファイル(state.json)を更新しました。")
    except Exception as e:
        log(f"履歴ファイルの保存に失敗しました: {e}", "ERROR")


def send_to_discord(webhook_url: str, embeds: list) -> bool:
    """Discord Webhookに安全にEmbedを送信する（レートリミット対策完備）"""
    payload = {
        "username": "Gizmodo 新着BOT",
        "avatar_url": "https://www.gizmodo.jp/favicon.ico",
        "embeds": embeds
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT
        },
        method="POST"
    )

    max_retries = 5
    delay = 1.0

    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status in (200, 204):
                    log(f"Discord通知に成功しました ({len(embeds)}件のEmbeds)")
                    return True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            
            if e.code == 429:
                retry_after = 5.0
                try:
                    resp_json = json.loads(body)
                    retry_after = float(resp_json.get("retry_after", 5.0))
                except Exception:
                    retry_after = float(e.headers.get("Retry-After", 5.0))
                
                log(f"Discordがレートリミットに達しました。 {retry_after}秒間スリープします。(試行 {attempt}/{max_retries})", "WARNING")
                time.sleep(retry_after)
                continue
            elif e.code == 403:
                log(f"Discordから 403 Forbidden が返されました。Webhook URLが無効か、ブロックされている可能性があります。レスポンス: {body}", "ERROR")
                return False
            elif e.code == 400:
                log(f"Discordから 400 Bad Request が返されました。ペイロードに問題があります。レスポンス: {body}", "ERROR")
                return False
            elif e.code >= 500:
                log(f"Discordサーバーエラー (HTTP {e.code})。{delay}秒後に再試行します。レスポンス: {body}", "WARNING")
                time.sleep(delay)
                delay *= 2
                continue
            else:
                log(f"Discord送信エラー (HTTP {e.code}): {e.reason}. レスポンス: {body}", "ERROR")
                return False
        except Exception as e:
            log(f"Discord通信中に例外が発生しました: {e}。{delay}秒後に再試行します。", "WARNING")
            time.sleep(delay)
            delay *= 2

    log("Discordへの送信リトライ上限に達したため失敗しました。", "ERROR")
    return False


def build_embed(article: dict) -> dict:
    """記事情報からDiscord用のEmbedを作成する"""
    color_hex = 1507330  # ギズモードレッド
    return {
        "title": article["title"],
        "url": article["link"],
        "description": article["description"],
        "color": color_hex,
        "author": {"name": article["author"]},
        "footer": {"text": f"Gizmodo Japan • {article['pub_date']}"}
    }


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log("環境変数 DISCORD_WEBHOOK_URL が設定されていません。処理を中断します。", "ERROR")
        return

    notified_urls = load_state()
    is_initial_run = (len(notified_urls) == 0)

    articles = fetch_rss_feed(RSS_URL)
    if not articles:
        log("新規記事の取得がスキップされたか、記事が0件です。")
        return

    new_articles = []
    for art in articles:
        if art["link"] not in notified_urls:
            new_articles.append(art)

    if not new_articles:
        log("新着記事はありません。")
        return

    log(f"新着記事を {len(new_articles)} 件検知しました。")

    if is_initial_run:
        log("初回実行のため、現在の全記事を『通知済み』として保存し、通知はスキップします。", "INFO")
        all_links = [art["link"] for art in articles]
        save_state(all_links)
        return

    new_articles.reverse()

    embeds_to_send = []
    processed_links = []

    for art in new_articles[:MAX_EMBEDS]:
        embeds_to_send.append(build_embed(art))
        processed_links.append(art["link"])

    if embeds_to_send:
        success = send_to_discord(webhook_url, embeds_to_send)
        if success:
            notified_urls.extend(processed_links)
            save_state(notified_urls)
        else:
            log("Discordへの通知に失敗したため、履歴の更新をスキップしました。", "WARNING")


if __name__ == "__main__":
    main()
