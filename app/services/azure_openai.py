from openai import AzureOpenAI
from app.config import settings
from app.services.prompt_loader import load_prompt
from typing import List, Generator
import logging

logger = logging.getLogger(__name__)


class AzureOpenAIService:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
        self.deployment_name = settings.AZURE_OPENAI_DEPLOYMENT_NAME

    def generate_summary(self, transcription: str, template_prompt: str | None = None) -> str:
        try:
            # 優先順位: 1) API引数 template_prompt  2) ファイルから読み込み  3) フォールバック
            if template_prompt and template_prompt.strip():
                prompt = template_prompt.strip()
                logger.info("Using template_prompt from API request")
            else:
                file_prompt = load_prompt()  # app/prompts/summary_default.md
                if file_prompt:
                    prompt = file_prompt
                    logger.info("Using prompt from file: summary_default.md")
                else:
                    # フォールバック（ファイルが見つからない場合）
                    prompt = "あなたは議事録を要約する専門家です。会議の文字起こしデータを構造化された議事録形式に変換してください。"
                    logger.warning("Prompt file not found, using fallback prompt")

            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"以下の会議文字起こしデータを構造化された議事録に変換してください:\n\n{transcription}"}
                ],
                temperature=0.3,
                max_tokens=8000
            )

            summary = response.choices[0].message.content
            logger.info(f"Summary generated: {len(summary)} characters")
            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            raise
    
    def chat_rewrite(
        self, 
        messages: List[dict], 
        streaming: bool = False
    ):
        """
        対話型リライト機能
        
        Args:
            messages: 対話履歴を含むメッセージリスト
            streaming: ストリーミングレスポンスを使用するか
        
        Returns:
            修正された議事録（ストリーミングの場合はジェネレーター）
        """
        try:
            if streaming:
                return self._chat_rewrite_streaming(messages)
            else:
                return self._chat_rewrite_normal(messages)
        
        except Exception as e:
            logger.error(f"Error in chat rewrite: {e}")
            raise
    
    def _chat_rewrite_normal(self, messages: List[dict]) -> str:
        """非ストリーミングのチャットリライト"""
        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            temperature=0.3,
            max_tokens=3000
        )
        
        content = response.choices[0].message.content
        logger.info(f"Chat rewrite completed: {len(content)} characters")
        return content
    
    def _chat_rewrite_streaming(self, messages: List[dict]) -> Generator[str, None, None]:
        """ストリーミングのチャットリライト"""
        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            temperature=0.3,
            max_tokens=3000,
            stream=True
        )
        
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


_azure_openai_service = None


def get_azure_openai_service() -> AzureOpenAIService:
    global _azure_openai_service
    if _azure_openai_service is None:
        _azure_openai_service = AzureOpenAIService()
    return _azure_openai_service
