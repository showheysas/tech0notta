"""
Zoom ゲスト参加Bot
Playwrightを使ってZoom Webクライアント経由でゲスト参加し、会議終了まで待機する
"""
import logging
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# セレクタ定数（Zoom Web UIの変更に追従するため適宜更新）
SELECTORS = {
    # 「ブラウザから参加」リンク（アプリ起動画面をスキップ）
    "join_from_browser": (
        'a:has-text("Join from your Browser"), '
        'a:has-text("ブラウザから参加"), '
        'a:has-text("Join from Your Browser")'
    ),
    # 名前入力フィールド
    "name_input": (
        'input#inputname, '
        'input[placeholder="Your Name"], '
        'input[placeholder="お名前"], '
        'input[placeholder="名前"]'
    ),
    # 参加ボタン（名前入力後）
    "join_button": (
        'button#joinBtn, '
        'button.preview-join-button, '
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


class ZoomBot:
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
                        const stream = await orig(constraints);
                        const audioTracks = stream.getAudioTracks();
                        if (audioTracks.length > 0) {
                            try {
                                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                                const dest = ctx.createMediaStreamDestination();
                                const silentTrack = dest.stream.getAudioTracks()[0];
                                audioTracks.forEach(t => { stream.removeTrack(t); t.stop(); });
                                if (silentTrack) stream.addTrack(silentTrack);
                            } catch(e) {
                                audioTracks.forEach(t => { t.enabled = false; });
                            }
                        }
                        return stream;
                    };
                })();
            """)

            try:
                logger.info(f"🌐 Zoom 会議URLに移動: {self.meeting_url}")
                page.goto(self.meeting_url, wait_until="domcontentloaded", timeout=60000)
                logger.info(f"📄 ページタイトル: {page.title()}")

                # 「ブラウザから参加」をクリック（デスクトップアプリ起動をスキップ）
                self._click_join_from_browser(page)

                # 名前を入力
                logger.info("👤 名前入力中...")
                self._enter_name(page)

                # 参加ボタンをクリック
                self._click_join(page)

                # 音声ダイアログを処理（必要なら閉じる）
                self._handle_audio_dialog(page)

                # 会議終了まで待機
                self._wait_for_meeting_end(page)

            except Exception as e:
                logger.error(f"Zoom Bot エラー: {e}")
                raise
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
                time.sleep(2)
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
                SELECTORS["join_button"], timeout=20000
            )
            if join_btn and join_btn.is_visible():
                join_btn.click()
                logger.info("✅ 参加ボタンクリック完了")
                time.sleep(3)
        except PlaywrightTimeoutError:
            logger.error("❌ 参加ボタンが見つかりませんでした")
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
