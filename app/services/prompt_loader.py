"""
プロンプトテンプレート管理サービス

app/prompts/ ディレクトリからプロンプトテンプレートを読み込む。
テンプレートはMarkdownファイルとして管理し、要約実行時に参照する。
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# プロンプトディレクトリのパス
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# デフォルトの要約プロンプトファイル名
DEFAULT_SUMMARY_PROMPT = "summary_default.md"


def load_prompt(filename: str = DEFAULT_SUMMARY_PROMPT) -> Optional[str]:
    """
    プロンプトテンプレートファイルを読み込む

    Args:
        filename: プロンプトファイル名（app/prompts/ 配下）

    Returns:
        プロンプト文字列。ファイルが見つからない場合はNone
    """
    filepath = PROMPTS_DIR / filename
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        logger.info(f"Prompt loaded from {filepath} ({len(content)} chars)")
        return content
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {filepath}")
        return None
    except Exception as e:
        logger.error(f"Error loading prompt from {filepath}: {e}")
        return None


def list_prompts() -> list[dict]:
    """
    利用可能なプロンプトテンプレート一覧を返す

    Returns:
        [{"filename": "summary_default.md", "name": "summary_default", "size": 1234}, ...]
    """
    prompts = []
    if not PROMPTS_DIR.exists():
        return prompts
    for f in sorted(PROMPTS_DIR.glob("*.md")):
        prompts.append({
            "filename": f.name,
            "name": f.stem,
            "size": f.stat().st_size,
        })
    return prompts
