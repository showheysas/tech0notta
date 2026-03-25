"""Notion コンテンツ変換 - Markdown → Notion blocks"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_summary(summary: str) -> dict:
    """
    要約テキストを ## / ### ヘッダーでセクション分割する。
    新フォーマット（アジェンダ、詳細論点、ネクストアクション、参加者別質問）と
    旧フォーマット（概要、主な議題、決定事項、アクションアイテム、次回の議題）の
    両方に対応する。
    """
    sections = {}
    current_section = None
    current_content = []

    for line in summary.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            if stripped.startswith("### "):
                current_section = stripped[4:].strip()
            else:
                current_section = stripped[3:].strip()
            current_content = []
        elif current_section is not None:
            current_content.append(line.rstrip())

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


def content_to_blocks(content: str) -> list:
    """
    セクション内容をNotionブロックのリストに変換する。
    Markdownテーブルを検出したらNotion tableブロックに変換し、
    それ以外はparagraphブロックにする。
    """
    blocks = []
    lines = content.split("\n")
    i = 0
    text_buffer = []

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("|") and line.strip().endswith("|"):
            if text_buffer:
                _flush_text_buffer(text_buffer, blocks)
                text_buffer = []

            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1

            table_block = markdown_table_to_notion(table_lines)
            if table_block:
                blocks.append(table_block)
        else:
            text_buffer.append(line)
            i += 1

    if text_buffer:
        _flush_text_buffer(text_buffer, blocks)

    return blocks


def _flush_text_buffer(text_buffer: list, blocks: list):
    """テキストバッファをparagraphブロックとしてflush"""
    text = "\n".join(text_buffer).strip()
    if not text:
        return
    if len(text) > 2000:
        for j in range(0, len(text), 2000):
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": text[j:j+2000]}}]
                }
            })
    else:
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        })


def markdown_table_to_notion(table_lines: list) -> Optional[dict]:
    """
    Markdownテーブル行のリストをNotion APIのtableブロックに変換する。
    """
    if len(table_lines) < 2:
        return None

    rows = []
    for line in table_lines:
        stripped = line.strip().strip("|").strip()
        if all(c in "-| :" for c in stripped):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return None

    max_cols = max(len(row) for row in rows)

    table_rows = []
    for row in rows:
        while len(row) < max_cols:
            row.append("")

        cells = []
        for cell_text in row[:max_cols]:
            rich_texts = parse_cell_rich_text(cell_text)
            cells.append(rich_texts)

        table_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": cells
            }
        })

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": max_cols,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows
        }
    }


def parse_cell_rich_text(text: str) -> list:
    """
    セルテキストをNotion rich_textに変換する。
    **太字** をboldアノテーションに変換。
    <br> を改行に変換。
    """
    text = re.sub(r'<br\s*/?>', '\n', text)

    result = []
    parts = re.split(r'(\*\*[^*]+\*\*)', text)

    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            result.append({
                "type": "text",
                "text": {"content": part[2:-2]},
                "annotations": {"bold": True}
            })
        else:
            result.append({
                "type": "text",
                "text": {"content": part}
            })

    if not result:
        result.append({"type": "text", "text": {"content": ""}})

    return result


def build_meeting_content(summary: str, metadata: dict) -> list:
    """議事録ページのコンテンツを構築（新フォーマット対応・テーブル変換あり）"""
    children = []

    participants = metadata.get("participants", [])
    if participants:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "参加者"}}]
            }
        })
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "、".join(participants)}}]
            }
        })

    sections = parse_summary(summary)

    for section_title, content in sections.items():
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": section_title}}]
            }
        })
        content_blocks = content_to_blocks(content)
        children.extend(content_blocks)

    return children
