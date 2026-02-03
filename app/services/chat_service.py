from sqlalchemy.orm import Session
from app.models.chat import ChatSession, ChatMessage
from app.models.job import Job, JobStatus
from app.services.azure_openai import get_azure_openai_service
from typing import List, Generator
import uuid
import logging

logger = logging.getLogger(__name__)


class ChatError(Exception):
    """チャット機能のエラー"""
    pass


class SessionNotFoundError(ChatError):
    """セッションが見つからない"""
    pass


class JobNotFoundError(ChatError):
    """Jobが見つからない"""
    pass


class InvalidMessageError(ChatError):
    """無効なメッセージ"""
    pass


class ChatService:
    """チャット機能のビジネスロジックを管理"""
    
    def __init__(self, db: Session):
        self.db = db
        self.openai_service = get_azure_openai_service()
    
    def create_session(self, job_id: str) -> ChatSession:
        """チャットセッションを作成"""
        # Jobの存在確認
        job = self.db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise JobNotFoundError(f"Job not found: {job_id}")
        
        # 要約が生成されているか確認
        if not job.summary:
            raise InvalidMessageError("Summary not generated yet")
        
        # セッション作成
        session_id = str(uuid.uuid4())
        session = ChatSession(
            session_id=session_id,
            job_id=job_id
        )
        
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        logger.info(f"Chat session created: {session_id} for job: {job_id}")
        return session
    
    def get_session(self, session_id: str) -> ChatSession:
        """セッションを取得"""
        session = self.db.query(ChatSession).filter(
            ChatSession.session_id == session_id
        ).first()
        
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        
        return session
    
    def send_message(
        self, 
        session_id: str, 
        user_message: str, 
        streaming: bool = False
    ):
        """
        ユーザーメッセージを送信し、AIの応答を取得
        
        Args:
            session_id: セッションID
            user_message: ユーザーのメッセージ
            streaming: ストリーミングレスポンスを使用するか
        
        Returns:
            ストリーミングの場合はジェネレーター、それ以外は文字列
        """
        # セッション取得
        session = self.get_session(session_id)
        
        # Job取得
        job = self.db.query(Job).filter(Job.job_id == session.job_id).first()
        if not job or not job.summary:
            raise JobNotFoundError("Job or summary not found")
        
        # コンテキスト構築（ユーザーメッセージ保存前に実行）
        context = self.build_context(session_id, job.summary, user_message)
        
        # ユーザーメッセージを保存
        user_msg_id = str(uuid.uuid4())
        user_msg = ChatMessage(
            message_id=user_msg_id,
            session_id=session_id,
            role="user",
            content=user_message
        )
        self.db.add(user_msg)
        self.db.commit()
        
        # AI応答生成
        if streaming:
            return self._generate_streaming_response(session_id, context)
        else:
            return self._generate_response(session_id, context)
    
    def _generate_response(self, session_id: str, context: List[dict]) -> str:
        """非ストリーミングレスポンスを生成"""
        try:
            response_content = self.openai_service.chat_rewrite(context, streaming=False)
            
            # アシスタントメッセージを保存
            assistant_msg_id = str(uuid.uuid4())
            assistant_msg = ChatMessage(
                message_id=assistant_msg_id,
                session_id=session_id,
                role="assistant",
                content=response_content
            )
            self.db.add(assistant_msg)
            self.db.commit()
            
            logger.info(f"Chat response generated for session: {session_id}")
            return response_content
            
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            raise ChatError(f"Failed to generate response: {str(e)}")
    
    def _generate_streaming_response(
        self, 
        session_id: str, 
        context: List[dict]
    ) -> Generator[str, None, None]:
        """ストリーミングレスポンスを生成"""
        try:
            full_content = ""
            for chunk in self.openai_service.chat_rewrite(context, streaming=True):
                full_content += chunk
                yield chunk
            
            # 完了後にアシスタントメッセージを保存
            assistant_msg_id = str(uuid.uuid4())
            assistant_msg = ChatMessage(
                message_id=assistant_msg_id,
                session_id=session_id,
                role="assistant",
                content=full_content
            )
            self.db.add(assistant_msg)
            self.db.commit()
            
            logger.info(f"Streaming chat response completed for session: {session_id}")
            
        except Exception as e:
            logger.error(f"Error in streaming response: {e}")
            raise ChatError(f"Failed to generate streaming response: {str(e)}")
    
    def get_messages(self, session_id: str) -> List[ChatMessage]:
        """チャット履歴を取得"""
        session = self.get_session(session_id)
        
        messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at).all()
        
        return messages
    
    def build_context(
        self, 
        session_id: str, 
        original_summary: str, 
        user_message: str
    ) -> List[dict]:
        """
        過去の対話履歴を含むコンテキストを構築
        
        Args:
            session_id: セッションID
            original_summary: 元の議事録
            user_message: 新しいユーザーメッセージ
        
        Returns:
            OpenAI APIに渡すメッセージリスト
        """
        SYSTEM_PROMPT = """あなたは議事録の修正を支援するAIアシスタントです。

【役割】
- ユーザーの指示に従って、議事録を修正・改善する
- 元の議事録の重要な情報を失わないように注意する
- 指示が曖昧な場合は、最も合理的な解釈で対応する

【対応可能な指示の例】
- 「要約を短くして」→ 簡潔にまとめる
- 「もっと詳しく」→ 詳細を追加
- 「箇条書きにして」→ フォーマットを変更
- 「決定事項を強調して」→ 特定セクションを強調
- 「〇〇の部分を削除」→ 指定部分を削除
- 「〇〇について追加」→ 指定内容を追加

【出力形式】
- 修正後の議事録全体を出力
- 元のフォーマット（Markdown）を維持
- 変更箇所が明確になるように配慮

【注意事項】
- 事実と異なる情報を追加しない
- 元の議事録の文脈を尊重する
- ユーザーの指示に忠実に従う
"""
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        # 過去のメッセージを取得（最新5件のみ）
        past_messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.desc()).limit(10).all()
        
        past_messages = list(reversed(past_messages))  # 古い順に並び替え
        
        # 最初のメッセージの場合、元の議事録を含める
        if not past_messages:
            messages.append({
                "role": "user",
                "content": f"以下の議事録を修正してください:\n\n{original_summary}"
            })
        else:
            # 過去の対話履歴を追加（最新5件のみ）
            for msg in past_messages[-5:]:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # 新しいユーザーメッセージを追加
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    def list_sessions(self, job_id: str = None) -> List[dict]:
        """セッション一覧を取得"""
        query = self.db.query(ChatSession)
        
        if job_id:
            query = query.filter(ChatSession.job_id == job_id)
        
        sessions = query.order_by(ChatSession.created_at.desc()).all()
        
        result = []
        for session in sessions:
            message_count = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.session_id
            ).count()
            
            result.append({
                "session_id": session.session_id,
                "job_id": session.job_id,
                "message_count": message_count,
                "created_at": session.created_at,
                "updated_at": session.updated_at
            })
        
        return result
