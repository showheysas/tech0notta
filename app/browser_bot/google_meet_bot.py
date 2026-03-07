"""
Google Meet ゲスト参加Bot
Playwrightを使ってGoogle Meetにゲスト（Googleアカウント不要）として参加し、
会議終了まで待機する
"""
import logging
import os
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# セレクタ定数（Google MeetのUI変更に追従するため適宜更新）
SELECTORS = {
    # ゲストとして続行ボタン（サインイン促進ダイアログ）
    "guest_option": (
        'button:has-text("Continue as a guest"), '
        'button:has-text("ゲストとして続行"), '
        'button:has-text("Continue without an account"), '
        'button:has-text("アカウントなしで続行"), '
        'button:has-text("Use without an account"), '
        'button:has-text("Use Meet without an account")'
    ),
    # 名前入力フィールド（ゲスト参加時）
    "name_input": (
        'input[placeholder="名前"], '
        'input[placeholder="Your name"], '
        'input[aria-label="Your name"], '
        'input[placeholder="あなたの名前"], '
        'input[type="text"][aria-label*="name" i], '
        'input[type="text"][data-placeholder*="name" i]'
    ),
    # 参加ボタン（待機室 or 直接参加）
    "join_button": (
        'button[jsname="Qx7uuf"], '
        'button[data-idom-class*="join"], '
        'button:has-text("Ask to join"), '
        'button:has-text("Join now"), '
        'button:has-text("今すぐ参加"), '
        'button:has-text("参加をリクエスト"), '
        'button:has-text("参加"), '
        'button[aria-label*="join" i], '
        'button[aria-label*="参加"]'
    ),
    # マイクオフボタン（参加前プレビュー画面）
    "mic_off": (
        'button[aria-label="Turn off microphone"], '
        'button[aria-label="マイクをオフにする"], '
        'button[aria-label*="microphone" i][data-is-muted="false"], '
        'button[aria-label*="マイク"][data-is-muted="false"]'
    ),
    # カメラオフボタン（参加前プレビュー画面）
    "camera_off": (
        'button[aria-label="Turn off camera"], '
        'button[aria-label="カメラをオフにする"], '
        'button[aria-label*="camera" i][data-is-muted="false"], '
        'button[aria-label*="カメラ"][data-is-muted="false"]'
    ),
    # 会議中のマイクONボタン（クリックするとミュートになる）
    "mic_on_in_meeting": (
        'button[aria-label="Turn off microphone (⌘D)"], '
        'button[aria-label="マイクをオフにする (⌘D)"], '
        'button[aria-label="Turn off microphone"], '
        'button[aria-label="マイクをオフにする"], '
        'button[jsname="BOHaEe"][data-is-muted="false"]'
    ),
    # 会議終了検知テキスト
    "call_ended": (
        'text="You\'ve left the call", '
        'text="This call has ended", '
        'text="通話が終了しました", '
        'text="退出しました", '
        'text="You left the meeting", '
        'text="Return to home screen"'
    ),
}


class GoogleMeetBot:
    def __init__(self, meeting_url: str, bot_name: str, timeout_min: int = 180):
        self.meeting_url = meeting_url
        self.bot_name = bot_name
        self.timeout_sec = timeout_min * 60

    def _dump_page_state(self, page, label: str):
        """ページの状態をログに出力（デバッグ用）"""
        try:
            title = page.title()
            url = page.url
            # ページ内の主要なテキストを取得
            body_text = page.evaluate("() => document.body ? document.body.innerText.substring(0, 1500) : 'no body'")
            logger.info(f"📸 [{label}] URL={url}, Title={title}")
            logger.info(f"📸 [{label}] Body text (先頭1500文字):\n{body_text}")
            # ボタン一覧
            buttons = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button')).slice(0, 20).map(b => ({
                    text: b.innerText.substring(0, 50),
                    ariaLabel: b.getAttribute('aria-label') || '',
                    jsname: b.getAttribute('jsname') || '',
                    visible: b.offsetParent !== null
                }));
            }""")
            logger.info(f"📸 [{label}] Buttons ({len(buttons)}): {buttons}")
            # input一覧
            inputs = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).slice(0, 10).map(i => ({
                    type: i.type,
                    placeholder: i.placeholder || '',
                    ariaLabel: i.getAttribute('aria-label') || '',
                    visible: i.offsetParent !== null
                }));
            }""")
            logger.info(f"📸 [{label}] Inputs ({len(inputs)}): {inputs}")
        except Exception as e:
            logger.warning(f"📸 [{label}] ページ状態取得失敗: {e}")

    def run(self):
        fake_video = os.environ.get("FAKE_VIDEO_PATH", "/app/black.y4m")
        fake_audio = os.environ.get("FAKE_AUDIO_PATH", "/app/silent.wav")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,  # Xvfb上で動作
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--use-fake-device-for-media-stream",
                    f"--use-file-for-fake-video-capture={fake_video}",
                    f"--use-file-for-fake-audio-capture={fake_audio}",
                    "--disable-features=WebRtcHideLocalIpsWithMdns",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    # パフォーマンス最適化フラグ（起動・参加時間短縮）
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--no-first-run",
                    "--disable-extensions",
                    "--disable-default-apps",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-translate",
                    "--disable-hang-monitor",
                    "--metrics-recording-only",
                    "--safebrowsing-disable-auto-update",
                ]
            )
            context = browser.new_context(
                permissions=["microphone", "camera"],
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            # getUserMedia オーバーライドは削除
            # --use-file-for-fake-audio-capture=silent.wav が既に無音を提供するため、
            # audio:false にすると Google Meet が「マイク使用不可」と判断し
            # 参加UIが表示されなくなる問題があった

            try:
                logger.info(f"🌐 Google Meet に移動: {self.meeting_url}")
                # domcontentloaded を使用（Google Meet はSPAで永続WebSocket接続があるため
                # networkidle には到達しない → タイムアウトする）
                page.goto(self.meeting_url, wait_until="domcontentloaded", timeout=60000)
                # SPA描画の完了を待つ
                page.wait_for_load_state("load", timeout=30000)
                logger.info(f"📄 ページタイトル: {page.title()}")

                # ページ初期状態をダンプ（デバッグ）
                self._dump_page_state(page, "初期ロード後")

                # 「ゲストとして続行」ボタンがあればクリック
                self._handle_guest_option(page)

                # 「ゲストとして参加」または名前入力フィールドを待つ
                logger.info("👤 ゲスト名を入力中...")
                self._enter_name(page)

                # ページ状態をダンプ（名前入力後）
                self._dump_page_state(page, "名前入力後")

                # マイク・カメラをオフに
                self._disable_av(page)

                # 参加ボタンをクリック
                self._click_join(page)

                # 参加後にマイクをミュート（偽デバイスのトーンが参加者に聞こえるのを防ぐ）
                self._mute_after_join(page)

                # 会議終了まで待機
                self._wait_for_meeting_end(page)

            except Exception as e:
                # エラー時もページ状態をダンプ
                self._dump_page_state(page, "エラー発生時")
                logger.error(f"Google Meet Bot エラー: {e}")
                raise
            finally:
                browser.close()

    def _handle_guest_option(self, page):
        """「ゲストとして続行」ボタンがあればクリック（サインイン促進画面をスキップ）"""
        try:
            btn = page.wait_for_selector(SELECTORS["guest_option"], timeout=5000)
            if btn and btn.is_visible():
                btn.click()
                logger.info("👤 ゲストオプションを選択")
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                time.sleep(1)
        except PlaywrightTimeoutError:
            logger.info("ゲストオプションなし（既にゲスト画面 or ログイン済み）、スキップ")

    def _enter_name(self, page):
        """ゲスト名入力フィールドに Bot 名を入力"""
        try:
            name_field = page.wait_for_selector(
                SELECTORS["name_input"], timeout=15000
            )
            if name_field:
                name_field.fill(self.bot_name)
                logger.info(f"✏️ 名前入力完了: {self.bot_name}")
        except PlaywrightTimeoutError:
            logger.warning("⚠️ 名前入力フィールドなし — ページ状態を確認してください")

    def _disable_av(self, page):
        """マイク・カメラをオフにする（既にオフなら無視）"""
        for selector_key, label in [("mic_off", "マイク"), ("camera_off", "カメラ")]:
            try:
                # wait_for_selector で確実にボタンが表示されるまで待つ
                btn = page.wait_for_selector(SELECTORS[selector_key], timeout=5000)
                if btn and btn.is_visible():
                    btn.click()
                    logger.info(f"🔇 {label}をオフに設定")
            except PlaywrightTimeoutError:
                logger.debug(f"{label}ボタン未検出（既にオフの可能性）")
            except Exception as e:
                logger.debug(f"{label}オフ設定スキップ: {e}")

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

    def _click_join(self, page):
        """参加ボタンをクリック"""
        try:
            join_btn = page.wait_for_selector(
                SELECTORS["join_button"], timeout=20000
            )
            if join_btn:
                join_btn.click()
                logger.info("✅ 参加ボタンクリック完了")
                self._notify_joining()
                time.sleep(1)  # 参加処理の待機
        except PlaywrightTimeoutError:
            logger.error("❌ 参加ボタンが見つかりませんでした")
            raise

    def _mute_after_join(self, page):
        """会議参加後にマイクをミュートする（参加者にトーンが聞こえるのを防ぐ）"""
        try:
            # 会議UIのロードを wait_for_selector で確実に待つ
            btn = page.wait_for_selector(SELECTORS["mic_on_in_meeting"], timeout=10000)
            if btn and btn.is_visible():
                btn.click()
                logger.info("🔇 会議参加後にマイクをミュート完了")
            else:
                logger.info("🔇 会議参加後マイク: 既にミュート済み")
        except PlaywrightTimeoutError:
            logger.info("🔇 会議参加後マイクボタン未検出（既にミュート済みの可能性）")
        except Exception as e:
            logger.debug(f"参加後マイクミュートスキップ: {e}")

    def _wait_for_meeting_end(self, page):
        """会議終了まで待機（タイムアウトまたは終了検知）"""
        logger.info(f"⏳ 会議終了を待機中（最大 {self.timeout_sec // 60} 分）...")
        start_time = time.time()
        check_interval = 10  # 秒

        while time.time() - start_time < self.timeout_sec:
            # 会議終了テキストを検索
            try:
                ended_element = page.query_selector(SELECTORS["call_ended"])
                if ended_element and ended_element.is_visible():
                    logger.info("📵 会議終了を検知しました")
                    return
            except Exception:
                pass

            # ページが閉じられた場合
            if page.is_closed():
                logger.info("📵 ページが閉じられました")
                return

            elapsed = int(time.time() - start_time)
            logger.info(f"🎙️ 会議参加中... ({elapsed // 60}分{elapsed % 60}秒経過)")
            time.sleep(check_interval)

        logger.info(f"⏰ タイムアウト（{self.timeout_sec // 60}分）に達しました")
