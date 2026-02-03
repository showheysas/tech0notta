from openai import AzureOpenAI
from app.config import settings
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
            system_prompt = """あなたは議事録を要約する専門家です。
以下の議事録を、次の形式で要約してください:

## 概要
会議の全体的な目的と主なトピックを簡潔にまとめてください。

## 主な議題
- 議論された主要なトピックをリスト形式で記載
- それぞれのポイントについて簡潔に説明

## 決定事項
- 会議で決まった事項をリスト形式で記載
- 具体的な決定内容を明確に

## アクションアイテム
- 誰が何をいつまでにするかを明記
- フォローアップが必要な項目

## 次回の議題
- 次回の会議で取り上げるべき項目があれば記載

簡潔で分かりやすい日本語でまとめてください。"""

            prompt = template_prompt.strip() if template_prompt else system_prompt
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"以下の議事録を要約してください:\n\n{transcription}"}
                ],
                temperature=0.3,
                max_tokens=2000
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
