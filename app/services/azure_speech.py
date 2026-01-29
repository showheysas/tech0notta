import azure.cognitiveservices.speech as speechsdk
from app.config import settings
import logging
import tempfile
import os
import time

logger = logging.getLogger(__name__)


class AzureSpeechService:
    def __init__(self):
        self.speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION
        )
        self.speech_config.speech_recognition_language = "ja-JP"

    def transcribe_audio(self, audio_data: bytes, audio_format: str = "wav") -> str:
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f".{audio_format}"
            ) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name

            try:
                audio_config = speechsdk.audio.AudioConfig(filename=temp_file_path)
                return self._run_continuous_recognition(audio_config)
            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            raise

    def _run_continuous_recognition(self, audio_config) -> str:
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )

        done = False
        transcription_parts = []
        error_message = None

        def stop_cb(evt):
            nonlocal done
            done = True

        def recognized_cb(evt):
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                transcription_parts.append(evt.result.text)
                logger.info(f"Recognized: {evt.result.text}")
            elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                logger.warning(f"No speech recognized: {evt.result.no_match_details}")

        def canceled_cb(evt):
            nonlocal done, error_message
            if evt.reason == speechsdk.CancellationReason.Error:
                error_message = f"Error: {evt.error_details}"
                logger.error(error_message)
            done = True

        speech_recognizer.recognized.connect(recognized_cb)
        speech_recognizer.session_stopped.connect(stop_cb)
        speech_recognizer.canceled.connect(canceled_cb)

        speech_recognizer.start_continuous_recognition()

        while not done:
            time.sleep(0.5)

        speech_recognizer.stop_continuous_recognition()

        if error_message:
            raise Exception(error_message)

        transcription = " ".join(transcription_parts)
        logger.info(f"Transcription completed: {len(transcription)} characters")
        return transcription


_azure_speech_service = None


def get_azure_speech_service() -> AzureSpeechService:
    global _azure_speech_service
    if _azure_speech_service is None:
        _azure_speech_service = AzureSpeechService()
    return _azure_speech_service
