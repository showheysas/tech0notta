"""
Zoom ゲスト参加Bot
Playwrightを使ってZoom Webクライアント経由でゲスト参加し、会議終了まで待機する
"""
import logging
import os
import re
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# セレクタ定数（Zoom Web UIの変更に追従するため適宜更新）
SELECTORS = {
    # 「ブラウザから参加」リンク（アプリ起動画面をスキップ）
    "join_from_browser": (
        'a:has-text("Join from your Browser"), '
        'a:has-text("ブラウザから参加"), '
        'a:has-text("Join from Your Browser"), '
        'a:has-text("join from your browser"), '
        'a[href*="wc/join"], '
        '#webclient'
    ),
    # 名前入力フィールド
    "name_input": (
        'input#inputname, '
        'input[placeholder="Your Name"], '
        'input[placeholder="Your name"], '
        'input[placeholder="お名前"], '
        'input[placeholder="名前"], '
        'input[aria-label*="name" i]'
    ),
    # 参加ボタン（名前入力後）
    "join_button": (
        'button#joinBtn, '
        'button.preview-join-button, '
        'button.zm-btn--primary:has-text("Join"), '
        'button.zm-btn--primary:has-text("参加"), '
        'button[class*="join"]:visible, '
        'button:has-text("Join"), '
        'button:has-text("参加")'
    ),
    # 音声ダイアログの「コンピューターのオーディオに参加」
    "join_audio": (
        'button:has-text("Join Audio by Computer"), '
        'button:has-text("コンピューターオーディオに参加"), '
        'button.join-audio-by-voip__join-btn'
    ),
    # 音声ダイアログを閉じる（「後で」「Skip」など）
    "skip_audio": (
        'button:has-text("No, Thanks"), '
        'button:has-text("後で"), '
        'button:has-text("Skip")'
    ),
    # 会議終了検知
    "meeting_ended": (
        'text="This meeting has been ended by the host", '
        'text="ホストによって会議が終了されました", '
        'text="Meeting is ended", '
        '.meeting-ended-dialog, '
        '.zm-modal-body-title:has-text("ended")'
    ),
}

# Bot検知回避用のステルススクリプト
STEALTH_SCRIPT = """
(() => {
    // navigator.webdriver を false に
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
        configurable: true,
    });

    // Chrome オブジェクトを偽装
    window.chrome = {
        runtime: {},
        loadTimes: function() { return {}; },
        csi: function() { return {}; },
    };

    // plugins を偽装（空だとBot扱いされる）
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ];
            plugins.length = 3;
            return plugins;
        },
        configurable: true,
    });

    // languages を設定
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'ja'],
        configurable: true,
    });

    // permissions.query のオーバーライド
    const origQuery = window.Permissions?.prototype?.query;
    if (origQuery) {
        window.Permissions.prototype.query = function(parameters) {
            if (parameters.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission });
            }
            return origQuery.call(this, parameters);
        };
    }
})();
"""


def _build_wc_url(meeting_url: str) -> str:
    """
    Zoom URLを Web Client URL（/wc/join/）形式に変換する。
    /wc/join/ はブラウザ参加に直接遷移し、Cloudflareチャレンジを回避できる可能性がある。
    """
    # 既に /wc/ 形式ならそのまま
    if '/wc/' in meeting_url:
        return meeting_url

    # https://us05web.zoom.us/j/12345678?pwd=xxx
    # → https://us05web.zoom.us/wc/join/12345678?pwd=xxx
    m = re.match(r'(https?://[^/]+)/j/(\d+)(.*)', meeting_url)
    if m:
        wc_url = f"{m.group(1)}/wc/join/{m.group(2)}{m.group(3)}"
        return wc_url

    return meeting_url


class ZoomBot:
    def __init__(self, meeting_url: str, bot_name: str, timeout_min: int = 180):
        self.meeting_url = meeting_url
        self.bot_name = bot_name
        self.timeout_sec = timeout_min * 60

    def _get_page_state_str(self, page) -> str:
        """ページの状態を文字列で返す（エラー報告用）"""
        try:
            url = page.url
            title = page.title()
            body = page.evaluate("() => document.body ? document.body.innerText.substring(0, 800) : 'no body'")
            buttons = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button')).slice(0, 15).map(b =>
                    `[btn] text="${b.innerText.substring(0,40)}" id=${b.id} class=${b.className.substring(0,60)} visible=${b.offsetParent!==null}`
                ).join('\\n');
            }""")
            inputs = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).slice(0, 8).map(i =>
                    `[input] type=${i.type} id=${i.id} placeholder="${i.placeholder}" visible=${i.offsetParent!==null}`
                ).join('\\n');
            }""")
            links = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).slice(0, 10).map(a =>
                    `[a] text="${a.innerText.substring(0,40)}" href=${(a.href||'').substring(0,80)} visible=${a.offsetParent!==null}`
                ).join('\\n');
            }""")
            return f"URL={url}\nTitle={title}\nBody:\n{body}\n\nButtons:\n{buttons}\n\nInputs:\n{inputs}\n\nLinks:\n{links}"
        except Exception as e:
            return f"Page state capture failed: {e}"

    def _dump_page_state(self, page, label: str):
        """ページの状態をログに出力（デバッグ用）"""
        try:
            title = page.title()
            url = page.url
            body_text = page.evaluate("() => document.body ? document.body.innerText.substring(0, 1500) : 'no body'")
            logger.info(f"📸 [{label}] URL={url}, Title={title}")
            logger.info(f"📸 [{label}] Body text (先頭1500文字):\n{body_text}")
            buttons = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button')).slice(0, 20).map(b => ({
                    text: b.innerText.substring(0, 50),
                    id: b.id || '',
                    className: b.className.substring(0, 80),
                    visible: b.offsetParent !== null
                }));
            }""")
            logger.info(f"📸 [{label}] Buttons ({len(buttons)}): {buttons}")
            inputs = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).slice(0, 10).map(i => ({
                    type: i.type,
                    id: i.id || '',
                    placeholder: i.placeholder || '',
                    ariaLabel: i.getAttribute('aria-label') || '',
                    visible: i.offsetParent !== null
                }));
            }""")
            logger.info(f"📸 [{label}] Inputs ({len(inputs)}): {inputs}")
            links = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).slice(0, 15).map(a => ({
                    text: a.innerText.substring(0, 50),
                    href: (a.href || '').substring(0, 100),
                    visible: a.offsetParent !== null
                }));
            }""")
            logger.info(f"📸 [{label}] Links ({len(links)}): {links}")
        except Exception as e:
            logger.warning(f"📸 [{label}] ページ状態取得失敗: {e}")

    def _notify_joining(self):
        """バックエンドに参加ボタンクリックを通知"""
        try:
            import httpx
            backend_url = os.environ.get('BACKEND_URL', '')
            session_id = os.environ.get('SESSION_ID', '')
            if backend_url and session_id:
                httpx.post(f"{backend_url}/api/bot/{session_id}/joining", timeout=5.0)
                logger.info("📡 バックエンドに参加通知を送信")
        except Exception as e:
            logger.warning(f"参加通知送信失敗（続行）: {e}")

    def _wait_for_cloudflare(self, page):
        """Cloudflareチャレンジページが表示された場合、解決を待つ"""
        try:
            title = page.title()
            if "just a moment" in title.lower() or "checking" in title.lower():
                logger.info("☁️ Cloudflareチャレンジを検出、解決を待機中...")
                # Cloudflareが自動解決するのを最大60秒待つ
                page.wait_for_function(
                    "() => !document.title.toLowerCase().includes('just a moment') "
                    "&& !document.title.toLowerCase().includes('checking')",
                    timeout=60000
                )
                logger.info(f"☁️ Cloudflareチャレンジ通過 → Title: {page.title()}")
                page.wait_for_load_state("load", timeout=30000)
                time.sleep(3)
        except PlaywrightTimeoutError:
            logger.warning("☁️ Cloudflareチャレンジ解決タイムアウト（60秒）、続行を試みます")

    def run(self):
        fake_video = os.environ.get("FAKE_VIDEO_PATH", "/app/black.y4m")
        fake_audio = os.environ.get("FAKE_AUDIO_PATH", "/app/silent.wav")

        # URLをWeb Client形式に変換（Cloudflare回避の可能性）
        wc_url = _build_wc_url(self.meeting_url)
        if wc_url != self.meeting_url:
            logger.info(f"🔗 Web Client URLに変換: {wc_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,  # Xvfb上で動作
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--use-fake-device-for-media-stream",
                    f"--use-file-for-fake-video-capture={fake_video}",
                    f"--use-file-for-fake-audio-capture={fake_audio}",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--window-size=1280,720",
                ]
            )
            context = browser.new_context(
                permissions=["microphone", "camera"],
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
                locale="en-US",
            )
            page = context.new_page()

            # Bot検知回避スクリプトを注入（ページ読み込み前に実行）
            page.add_init_script(STEALTH_SCRIPT)

            try:
                # まず /wc/join/ URL を試す（Cloudflare回避の可能性）
                logger.info(f"🌐 Zoom Web Client URLに移動: {wc_url}")
                page.goto(wc_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_load_state("load", timeout=30000)
                logger.info(f"📄 ページタイトル: {page.title()}")

                # Cloudflareチャレンジの検出と待機
                self._wait_for_cloudflare(page)

                # /wc/join/ がCloudflareでブロックされた場合、通常URLにフォールバック
                if wc_url != self.meeting_url and "just a moment" in page.title().lower():
                    logger.info("☁️ /wc/join/ がCloudflareにブロック、通常URLで再試行")
                    page.goto(self.meeting_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_load_state("load", timeout=30000)
                    self._wait_for_cloudflare(page)

                # ページ初期状態をダンプ（デバッグ）
                self._dump_page_state(page, "初期ロード後")

                # 「ブラウザから参加」をクリック（デスクトップアプリ起動をスキップ）
                # /wc/join/ 形式の場合はこのステップ不要の可能性あり
                self._click_join_from_browser(page)

                # ページ状態をダンプ（ブラウザ参加選択後）
                self._dump_page_state(page, "ブラウザ参加選択後")

                # 名前を入力
                logger.info("👤 名前入力中...")
                self._enter_name(page)

                # 参加ボタンをクリック
                self._click_join(page)

                # バックエンドに参加通知
                self._notify_joining()

                # 音声ダイアログを処理（必要なら閉じる）
                self._handle_audio_dialog(page)

                # 会議終了まで待機
                self._wait_for_meeting_end(page)

            except Exception as e:
                page_info = self._get_page_state_str(page)
                logger.error(f"Zoom Bot エラー: {e}\n{page_info}")
                raise RuntimeError(f"{e}\n--- Page State ---\n{page_info}") from e
            finally:
                browser.close()

    def _click_join_from_browser(self, page):
        """「ブラウザから参加」リンクをクリックしてアプリ起動をスキップ"""
        try:
            link = page.wait_for_selector(
                SELECTORS["join_from_browser"], timeout=15000
            )
            if link and link.is_visible():
                link.click()
                logger.info("🌐 ブラウザから参加を選択")
                page.wait_for_load_state("load", timeout=30000)
                time.sleep(3)
        except PlaywrightTimeoutError:
            logger.info("「ブラウザから参加」リンクなし、続行")

    def _enter_name(self, page):
        """名前入力フィールドにBot名を入力"""
        try:
            name_field = page.wait_for_selector(
                SELECTORS["name_input"], timeout=15000
            )
            if name_field:
                name_field.fill(self.bot_name)
                logger.info(f"✏️ 名前入力完了: {self.bot_name}")
        except PlaywrightTimeoutError:
            logger.info("名前入力フィールドなし、スキップ")

    def _click_join(self, page):
        """参加ボタンをクリック"""
        try:
            join_btn = page.wait_for_selector(
                SELECTORS["join_button"], timeout=30000
            )
            if join_btn and join_btn.is_visible():
                join_btn.click()
                logger.info("✅ 参加ボタンクリック完了")
                time.sleep(3)
        except PlaywrightTimeoutError:
            logger.error("❌ 参加ボタンが見つかりませんでした")
            self._dump_page_state(page, "参加ボタン未検出")
            raise

    def _handle_audio_dialog(self, page):
        """音声設定ダイアログが出た場合の処理（無音参加）"""
        try:
            # 「コンピューターオーディオに参加」があればクリック（ミュートのまま参加）
            audio_btn = page.wait_for_selector(
                SELECTORS["join_audio"], timeout=5000
            )
            if audio_btn and audio_btn.is_visible():
                audio_btn.click()
                logger.info("🔊 オーディオダイアログ: コンピューターオーディオに参加")
        except PlaywrightTimeoutError:
            # 「後で」「Skip」があれば閉じる
            try:
                skip_btn = page.query_selector(SELECTORS["skip_audio"])
                if skip_btn and skip_btn.is_visible():
                    skip_btn.click()
                    logger.info("🔕 オーディオダイアログをスキップ")
            except Exception:
                pass

    def _wait_for_meeting_end(self, page):
        """会議終了まで待機（タイムアウトまたは終了検知）"""
        logger.info(f"⏳ 会議終了を待機中（最大 {self.timeout_sec // 60} 分）...")
        start_time = time.time()
        check_interval = 10

        while time.time() - start_time < self.timeout_sec:
            try:
                ended_element = page.query_selector(SELECTORS["meeting_ended"])
                if ended_element and ended_element.is_visible():
                    logger.info("📵 会議終了を検知しました")
                    return
            except Exception:
                pass

            if page.is_closed():
                logger.info("📵 ページが閉じられました")
                return

            elapsed = int(time.time() - start_time)
            logger.info(f"🎙️ 会議参加中... ({elapsed // 60}分{elapsed % 60}秒経過)")
            time.sleep(check_interval)

        logger.info(f"⏰ タイムアウト（{self.timeout_sec // 60}分）に達しました")
