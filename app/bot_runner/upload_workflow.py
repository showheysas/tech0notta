#!/usr/bin/env python3
"""
録音ファイルアップロード & 自動文字起こし・要約ワークフロー
会議終了後に自動で実行され、録音ファイルをバックエンドにアップロードし、
文字起こしと要約（議事録作成）を行います。
"""
import os
import sys
import time
import glob
import logging
import httpx

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 設定
BACKEND_URL = os.environ.get('BACKEND_URL', 'http://host.docker.internal:8000')
RECORDINGS_DIR = os.environ.get('RECORDINGS_DIR', '/app/recordings')
POLL_INTERVAL = 5  # 文字起こし完了待機ポーリング間隔（秒）
POLL_TIMEOUT = 1800  # 最大待機時間（秒）


def find_latest_recording() -> str | None:
    """
    最新の録音ファイルを検索
    """
    pattern = os.path.join(RECORDINGS_DIR, "*.wav")
    files = glob.glob(pattern)
    
    if not files:
        return None
    
    # 更新日時が最新のファイルを返す
    return max(files, key=os.path.getmtime)


def upload_file(filepath: str) -> dict:
    """
    録音ファイルをバックエンドにアップロード
    """
    logger.info(f"📤 ファイルアップロード中: {filepath}")
    
    filename = os.path.basename(filepath)
    
    with open(filepath, 'rb') as f:
        files = {'file': (filename, f, 'audio/wav')}
        response = httpx.post(
            f"{BACKEND_URL}/api/upload",
            files=files,
            timeout=300  # 大きなファイル用に5分
        )
    
    response.raise_for_status()
    result = response.json()
    logger.info(f"✅ アップロード完了: job_id={result.get('job_id')}")
    return result


def trigger_transcription(job_id: str) -> dict:
    """
    文字起こしをトリガー
    """
    logger.info(f"🔊 文字起こし開始: job_id={job_id}")
    
    response = httpx.post(
        f"{BACKEND_URL}/api/transcribe",
        json={"job_id": job_id},
        timeout=60
    )
    
    response.raise_for_status()
    result = response.json()
    logger.info(f"✅ 文字起こしジョブ開始: {result}")
    return result


def wait_for_transcription(job_id: str) -> dict:
    """
    文字起こし完了を待機
    """
    logger.info(f"⏳ 文字起こし完了待機中: job_id={job_id}")
    
    start_time = time.time()
    
    while True:
        response = httpx.get(
            f"{BACKEND_URL}/api/transcribe/status",
            params={"job_id": job_id},
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        
        status = result.get("status")
        
        if status == "TRANSCRIBED":
            logger.info("✅ 文字起こし完了")
            return result
        elif status == "FAILED":
            error_msg = result.get("error_message", "Unknown error")
            logger.error(f"❌ 文字起こし失敗: {error_msg}")
            raise RuntimeError(f"Transcription failed: {error_msg}")
        
        # タイムアウトチェック
        elapsed = time.time() - start_time
        if elapsed > POLL_TIMEOUT:
            raise TimeoutError(f"Transcription timeout after {POLL_TIMEOUT} seconds")
        
        logger.info(f"   状態: {status} (経過: {int(elapsed)}秒)")
        time.sleep(POLL_INTERVAL)


def trigger_summarization(job_id: str) -> dict:
    """
    要約（議事録作成）をトリガー
    """
    logger.info(f"📝 要約（議事録作成）開始: job_id={job_id}")
    
    response = httpx.post(
        f"{BACKEND_URL}/api/summarize",
        json={"job_id": job_id},
        timeout=120
    )
    
    response.raise_for_status()
    result = response.json()
    logger.info(f"✅ 要約完了: status={result.get('status')}")
    return result


def main():
    """
    メイン処理
    """
    logger.info("=========================================")
    logger.info("  📤 録音アップロード & 自動処理ワークフロー")
    logger.info("=========================================")
    logger.info(f"  Backend URL: {BACKEND_URL}")
    logger.info(f"  Recordings Dir: {RECORDINGS_DIR}")
    logger.info("")
    
    # 最新の録音ファイルを検索
    recording_file = find_latest_recording()
    
    if not recording_file:
        logger.warning("⚠️ 録音ファイルが見つかりません")
        return 1
    
    logger.info(f"📁 録音ファイル発見: {recording_file}")
    
    try:
        # 1. アップロード
        upload_result = upload_file(recording_file)
        job_id = upload_result.get("job_id")
        
        if not job_id:
            logger.error("❌ job_id が取得できませんでした")
            return 1
        
        # 2. 文字起こし
        trigger_transcription(job_id)
        wait_for_transcription(job_id)
        
        # 3. 要約（議事録作成）
        summary_result = trigger_summarization(job_id)
        
        logger.info("")
        logger.info("=========================================")
        logger.info("  ✅ ワークフロー完了")
        logger.info("=========================================")
        logger.info(f"  Job ID: {job_id}")
        logger.info(f"  Status: {summary_result.get('status')}")
        logger.info("")
        
        return 0
        
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ API エラー: {e.response.status_code} - {e.response.text}")
        return 1
    except Exception as e:
        logger.error(f"❌ エラー: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
