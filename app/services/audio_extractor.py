"""
音声抽出サービス

動画ファイルから音声を抽出するサービス。
FFmpegを使用して動画ファイルをWAV形式の音声ファイルに変換します。
"""
import ffmpeg
import tempfile
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioExtractor:
    """動画から音声を抽出するクラス"""
    
    @staticmethod
    def is_video_file(content_type: str) -> bool:
        """
        ファイルが動画ファイルかどうかを判定
        
        Args:
            content_type: MIMEタイプ
            
        Returns:
            動画ファイルの場合True
        """
        video_types = [
            'video/mp4',
            'video/quicktime',
            'video/x-msvideo',
            'video/webm',
            'video/x-matroska'
        ]
        return content_type in video_types
    
    @staticmethod
    def extract_audio(input_data: bytes, input_filename: str) -> tuple[bytes, str]:
        """
        動画ファイルから音声を抽出
        
        Args:
            input_data: 入力動画ファイルのバイトデータ
            input_filename: 入力ファイル名（拡張子の判定に使用）
            
        Returns:
            (音声データ, 出力ファイル名) のタプル
            
        Raises:
            Exception: 音声抽出に失敗した場合
        """
        temp_input = None
        temp_output = None
        
        try:
            # 入力ファイルの拡張子を取得
            input_ext = Path(input_filename).suffix
            
            # 一時ファイルを作成（入力動画）
            with tempfile.NamedTemporaryFile(suffix=input_ext, delete=False) as temp_input_file:
                temp_input = temp_input_file.name
                temp_input_file.write(input_data)
            
            # 出力ファイル名を生成（WAV形式）
            output_filename = Path(input_filename).stem + '_extracted.wav'
            
            # 一時ファイルを作成（出力音声）
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output_file:
                temp_output = temp_output_file.name
            
            logger.info(f"Extracting audio from {input_filename}")
            
            # FFmpegで音声を抽出
            # - 音声コーデック: PCM 16-bit
            # - サンプリングレート: 16kHz（Azure Speech Serviceに最適）
            # - チャンネル: モノラル
            (
                ffmpeg
                .input(temp_input)
                .output(
                    temp_output,
                    acodec='pcm_s16le',  # PCM 16-bit
                    ar='16000',          # 16kHz
                    ac=1                 # モノラル
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )
            
            # 抽出された音声ファイルを読み込み
            with open(temp_output, 'rb') as f:
                audio_data = f.read()
            
            logger.info(f"Audio extracted successfully: {len(audio_data)} bytes")
            
            return audio_data, output_filename
            
        except ffmpeg.Error as e:
            error_message = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"FFmpeg error: {error_message}")
            raise Exception(f"Failed to extract audio: {error_message}")
            
        except Exception as e:
            logger.error(f"Error extracting audio: {e}")
            raise
            
        finally:
            # 一時ファイルを削除
            if temp_input and os.path.exists(temp_input):
                try:
                    os.unlink(temp_input)
                except Exception as e:
                    logger.warning(f"Failed to delete temp input file: {e}")
            
            if temp_output and os.path.exists(temp_output):
                try:
                    os.unlink(temp_output)
                except Exception as e:
                    logger.warning(f"Failed to delete temp output file: {e}")


# シングルトンインスタンス
_audio_extractor = AudioExtractor()


def get_audio_extractor() -> AudioExtractor:
    """AudioExtractorのシングルトンインスタンスを取得"""
    return _audio_extractor
