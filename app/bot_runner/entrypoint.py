#!/usr/bin/env python3
"""
Bot Runnerエントリポイント
環境変数から設定を読み込み、Zoom Meeting SDKを起動
"""
import os
import sys
import subprocess
import logging
import threading
import time

from config_generator import write_config_file

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def start_realtime_transcription(session_id: str) -> subprocess.Popen | None:
    """
    リアルタイム文字起こしプロセスを起動
    """
    backend_url = os.environ.get('BACKEND_URL', 'http://host.docker.internal:8000')
    speech_key = os.environ.get('AZURE_SPEECH_KEY')
    speech_region = os.environ.get('AZURE_SPEECH_REGION', 'japaneast')
    
    if not speech_key:
        logger.warning("⚠️ AZURE_SPEECH_KEY が設定されていないため、リアルタイム文字起こしをスキップ")
        return None
    
    logger.info("🎙️ リアルタイム文字起こしを開始...")
    
    env = os.environ.copy()
    env['SESSION_ID'] = session_id
    env['BACKEND_URL'] = backend_url
    env['AZURE_SPEECH_KEY'] = speech_key
    env['AZURE_SPEECH_REGION'] = speech_region
    
    # realtime_transcriber.py をサブプロセスとして起動
    process = subprocess.Popen(
        [sys.executable, '/app/realtime_transcriber.py'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    
    # ログ出力スレッド
    def log_output():
        for line in iter(process.stdout.readline, b''):
            logger.info(f"[TRANSCRIBER] {line.decode().rstrip()}")
    
    log_thread = threading.Thread(target=log_output, daemon=True)
    log_thread.start()
    
    return process


def main():
    """メイン処理"""
    logger.info("🤖 Tech Notta Bot Runner 起動")
    
    # 環境変数から設定を取得
    meeting_number = os.environ.get('MEETING_NUMBER')
    jwt_token = os.environ.get('JWT_TOKEN')
    password = os.environ.get('PASSWORD', '')
    bot_name = os.environ.get('BOT_NAME', 'Tech Bot')
    session_id = os.environ.get('SESSION_ID', '')
    
    # バリデーション
    if not meeting_number:
        logger.error("❌ MEETING_NUMBER が設定されていません")
        sys.exit(1)
    
    if not jwt_token:
        logger.error("❌ JWT_TOKEN が設定されていません")
        sys.exit(1)
    
    # SESSION_ID がなければ生成
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
        os.environ['SESSION_ID'] = session_id
    
    logger.info(f"📋 設定: meeting={meeting_number}, bot_name={bot_name}, session_id={session_id}")
    
    # PulseAudio設定
    logger.info("🔊 PulseAudio設定中...")
    subprocess.run(["/app/setup-pulseaudio.sh"], check=False)
    
    # config.txt生成
    config_path = "/app/sdk/config.txt"
    write_config_file(
        output_path=config_path,
        meeting_number=meeting_number,
        jwt_token=jwt_token,
        meeting_password=password,
        get_video=True,
        get_audio=True
    )
    
    # リアルタイム文字起こしプロセスを起動
    transcriber_process = start_realtime_transcription(session_id)
    
    # 録音プロセスを起動（audio_capture.sh）
    logger.info("🎙️ 音声キャプチャを開始...")
    audio_capture_process = subprocess.Popen(
        ['/app/audio_capture.sh'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    
    # 録音ロガスレッド
    def log_capture_output():
        if audio_capture_process.stdout:
            for line in iter(audio_capture_process.stdout.readline, b''):
                logger.info(f"[CAPTURE] {line.decode().rstrip()}")
    
    capture_log_thread = threading.Thread(target=log_capture_output, daemon=True)
    capture_log_thread.start()
    
    # SDK実行
    sdk_binary = "/app/zoom_bot"
    
    try:
        if not os.path.exists(sdk_binary):
            logger.warning(
                "⚠️ SDK バイナリが見つかりません。"
                "Zoom Marketplaceから Meeting SDK Linux をダウンロードし、"
                "/app/sdk/ に配置してください。"
            )
            logger.info("🔄 デモモード: SDK無しで動作確認中...")
            
            # デモモード: SDKなしで待機
            logger.info("✅ Bot参加シミュレーション開始")
            
            while True:
                logger.info(f"🎙️ 会議 {meeting_number} に参加中...")
                time.sleep(30)
        
        else:
            # 実際のSDK起動
            logger.info(f"🚀 SDK起動: {sdk_binary}")
            
            os.chdir("/app/sdk")
            result = subprocess.run(
                [sdk_binary],
                cwd="/app/sdk",
                capture_output=False
            )
            
            logger.info(f"SDK終了: return_code={result.returncode}")
    
    finally:
        # プロセス終了処理
        logger.info("🛑 クリーンアップ開始...")
        
        # 1. リアルタイム文字起こし停止
        if transcriber_process and transcriber_process.poll() is None:
            logger.info("  realtime_transcriber.py を停止中...")
            transcriber_process.terminate()
            transcriber_process.wait(timeout=5)
            
        # 2. 録音停止
        if audio_capture_process and audio_capture_process.poll() is None:
            logger.info("  audio_capture.sh を停止中...")
            audio_capture_process.terminate()
            audio_capture_process.wait(timeout=5)
            
        # 3. アップロードワークフロー実行
        logger.info("📤 自動アップロード & 議事録作成ワークフローを実行...")
        try:
            workflow_result = subprocess.run(
                [sys.executable, '/app/upload_workflow.py'],
                capture_output=True,
                text=True
            )
            if workflow_result.returncode == 0:
                logger.info("✅ ワークフロー正常終了")
                logger.info(workflow_result.stdout)
            else:
                logger.error(f"⚠️ ワークフロー失敗 (code: {workflow_result.returncode})")
                logger.error(workflow_result.stderr)
        except Exception as e:
            logger.error(f"ワークフロー実行エラー: {e}")




if __name__ == "__main__":
    main()

