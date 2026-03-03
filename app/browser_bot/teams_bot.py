"""
Microsoft Teams ゲスト参加Bot
Playwrightを使ってTeamsにゲスト（Microsoftアカウント不要）として参加し、
会議終了まで待機する
"""
import logging
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# セレクタ定数（TeamsのUI変更に追従するため適宜更新）
SELECTORS = {
    # 「代わりにWebで参加」リンク（アプリダウンロード画面をスキップ）
    "join_on_web": (
        'a:has-text("Continue on this browser"), '
        'a:has-text("このブラウザーで続ける"), '
        'button:has-text("Continue on this browser"), '
        'button:has-text("このブラウザーで続ける")'
    ),
    # 名前入力フィールド（ゲスト参加時）
    "name_input": (
        'input[placeholder="Type your name"], '
        'input[placeholder="名前を入力してください"], '
        'input[data-tid="prejoin-display-name-input"]'
    ),
    # 参加ボタン
    "join_button": (
        'button[data-tid="prejoin-join-button"], '
        'button:has-text("Join now"), '
        'button:has-text("今すぐ参加")'
    ),
    # マイクオフ（参加前）
    "mic_toggle": (
        'button[data-tid="toggle-mute"], '
        'button[aria-label*="mute"], '
        'button[aria-label*="マイク"]'
    ),
    # カメラオフ（参加前）
    "camera_toggle": (
        'button[data-tid="toggle-video"], '
        'button[aria-label*="camera"], '
        'button[aria-label*="カメラ"]'
    ),
    # 会議終了検知テキスト
    "call_ended": (
        'text="The meeting has ended", '
        'text="会議が終了しました", '
        'text="You left the meeting", '
        'text="会議から退出しました"'
    ),
}


class TeamsBot:
    def __init__(self, meeting_url: str, bot_name: str, timeout_min: int = 180):
        self.meeting_url = meeting_url
        self.bot_name = bot_name
        self.timeout_sec = timeout_min * 60

    def run(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,  # Xvfb上で動作
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--use-fake-device-for-media-stream",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            context = browser.new_context(
                permissions=["microphone", "camera"],
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            # ページコード実行前にgetUserMediaをオーバーライド（ビープ音対策）
            page.add_init_script("""
                (() => {
                    const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                    navigator.mediaDevices.getUserMedia = async function(constraints) {
                        const c = constraints ? Object.assign({}, constraints, {audio: false}) : constraints;
                        return await orig(c);
                    };
                })();
            """)

            try:
                logger.info(f"🌐 Teams 会議URLに移動: {self.meeting_url}")
                page.goto(self.meeting_url, wait_until="networkidle", timeout=30000)

                # 「Webで参加」を選択（アプリダウンロード画面をスキップ）
                self._click_join_on_web(page)

                # 名前入力
                self._enter_name(page)

                # マイク・カメラをオフに
                self._disable_av(page)

                # 参加ボタンをクリック
                self._click_join(page)

                # 会議終了まで待機
                self._wait_for_meeting_end(page)

            except Exception as e:
                logger.error(f"Teams Bot エラー: {e}")
                raise
            finally:
                browser.close()

    def _click_join_on_web(self, page):
        """「このブラウザーで続ける」をクリックしてアプリ誘導をスキップ"""
        try:
            web_btn = page.wait_for_selector(
                SELECTORS["join_on_web"], timeout=10000
            )
            if web_btn:
                web_btn.click()
                logger.info("🌐 Webで参加を選択")
                time.sleep(2)
        except PlaywrightTimeoutError:
            logger.info("Webで参加ボタンなし、続行")

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
            logger.info("名前入力フィールドなし、スキップ")

    def _disable_av(self, page):
        """マイク・カメラをオフにする"""
        for selector_key, label in [("mic_toggle", "マイク"), ("camera_toggle", "カメラ")]:
            try:
                btn = page.query_selector(SELECTORS[selector_key])
                if btn and btn.is_visible():
                    # aria-pressed="true" の場合はオンなのでクリックしてオフにする
                    pressed = btn.get_attribute("aria-pressed")
                    if pressed == "true":
                        btn.click()
                        logger.info(f"🔇 {label}をオフに設定")
                        time.sleep(0.5)
            except Exception as e:
                logger.debug(f"{label}オフ設定スキップ: {e}")

    def _click_join(self, page):
        """参加ボタンをクリック"""
        try:
            join_btn = page.wait_for_selector(
                SELECTORS["join_button"], timeout=20000
            )
            if join_btn:
                join_btn.click()
                logger.info("✅ 参加ボタンクリック完了")
                time.sleep(3)
        except PlaywrightTimeoutError:
            logger.error("❌ 参加ボタンが見つかりませんでした")
            raise

    def _wait_for_meeting_end(self, page):
        """会議終了まで待機"""
        logger.info(f"⏳ 会議終了を待機中（最大 {self.timeout_sec // 60} 分）...")
        start_time = time.time()
        check_interval = 10

        while time.time() - start_time < self.timeout_sec:
            try:
                ended_element = page.query_selector(SELECTORS["call_ended"])
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
