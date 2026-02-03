from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatHistoryResponse,
    ChatSessionListResponse,
    ChatSessionListItem
)
from app.services.chat_service import (
    ChatService,
    SessionNotFoundError,
    JobNotFoundError,
    InvalidMessageError,
    ChatError
)
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionResponse)
async def create_chat_session(
    request: ChatSessionCreate,
    db: Session = Depends(get_db)
):
    """チャットセッションを作成"""
    try:
        chat_service = ChatService(db)
        session = chat_service.create_session(request.job_id)
        
        return ChatSessionResponse(
            session_id=session.session_id,
            job_id=session.job_id,
            created_at=session.created_at,
            updated_at=session.updated_at
        )
    
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidMessageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create chat session")


@router.post("/sessions/{session_id}/messages")
async def send_chat_message(
    session_id: str,
    request: ChatMessageCreate,
    db: Session = Depends(get_db)
):
    """チャットメッセージを送信（リライト実行）"""
    try:
        chat_service = ChatService(db)
        
        if request.streaming:
            # ストリーミングレスポンス
            async def generate():
                try:
                    for chunk in chat_service.send_message(
                        session_id, 
                        request.message, 
                        streaming=True
                    ):
                        yield f"data: {json.dumps({'type': 'content', 'delta': chunk})}\n\n"
                    
                    yield f"data: {json.dumps({'type': 'end'})}\n\n"
                
                except Exception as e:
                    logger.error(f"Error in streaming: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
            return StreamingResponse(generate(), media_type="text/event-stream")
        
        else:
            # 非ストリーミングレスポンス
            response_content = chat_service.send_message(
                session_id, 
                request.message, 
                streaming=False
            )
            
            # 最新のアシスタントメッセージを取得
            messages = chat_service.get_messages(session_id)
            latest_assistant_msg = next(
                (msg for msg in reversed(messages) if msg.role == "assistant"),
                None
            )
            
            if not latest_assistant_msg:
                raise HTTPException(status_code=500, detail="Failed to retrieve response")
            
            return ChatMessageResponse(
                message_id=latest_assistant_msg.message_id,
                role=latest_assistant_msg.role,
                content=latest_assistant_msg.content,
                created_at=latest_assistant_msg.created_at
            )
    
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ChatError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending chat message: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.get("/sessions/{session_id}/messages", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    db: Session = Depends(get_db)
):
    """チャット履歴を取得"""
    try:
        chat_service = ChatService(db)
        session = chat_service.get_session(session_id)
        messages = chat_service.get_messages(session_id)
        
        return ChatHistoryResponse(
            session_id=session.session_id,
            job_id=session.job_id,
            messages=[
                ChatMessageResponse(
                    message_id=msg.message_id,
                    role=msg.role,
                    content=msg.content,
                    created_at=msg.created_at
                )
                for msg in messages
            ]
        )
    
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chat history")


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    job_id: str = None,
    db: Session = Depends(get_db)
):
    """セッション一覧を取得"""
    try:
        chat_service = ChatService(db)
        sessions = chat_service.list_sessions(job_id)
        
        return ChatSessionListResponse(
            sessions=[
                ChatSessionListItem(**session)
                for session in sessions
            ]
        )
    
    except Exception as e:
        logger.error(f"Error listing chat sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to list sessions")
