"""HKDSE Chinese Language — 中文科 API (Essay Grader, Paper Generator)."""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EssayGradeRequest(BaseModel):
    """中文作文批改请求"""
    title: str = ""                          # 作文题目
    essay: str                               # 学生作文全文
    genre: str = "argumentative"             # 文体: narrative | argumentative | descriptive


class DimensionScore(BaseModel):
    """单个评分维度"""
    score: int                               # 得分
    max_score: int                           # 满分
    comment: str                             # 评语


class EssayGradeResult(BaseModel):
    """中文作文批改结果"""
    content: DimensionScore                  # 内容 (40%)
    expression: DimensionScore               # 表达 (40%)
    organization: DimensionScore             # 组织 (20%)
    total_score: int
    max_score: int = 100
    percentage: float
    strengths: list[str]                     # 优点
    improvements: list[str]                  # 改进建议
    overall_comment: str                     # 总评
    annotated_text: str = ""                 # 带批注的原文


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_GENRE_LABELS: dict[str, str] = {
    "narrative": "記敘文",
    "argumentative": "議論文",
    "descriptive": "描寫文",
}

_RUBRIC = """HKDSE 中國語文科 卷二寫作能力 評分標準（滿分 100 分）：

一、內容（40 分）
- 立意深刻，取材恰當，能緊扣主題
- 內容充實，論據/事例具體有力
- 思考角度新穎，有個人見解

二、表達（40 分）
- 詞彙豐富，用詞精準
- 句式多變，修辭恰當
- 文筆流暢，表達清晰

三、組織（20 分）
- 結構完整（引言—正文—結論）
- 段落銜接自然，邏輯嚴密
- 詳略得當，層次分明"""


def _build_essay_grade_system_prompt() -> str:
    return """你是一位資深的 HKDSE 中文科閱卷員。請嚴格按照評分標準批改學生的作文。

對於每個評分維度，請給出具體的得分和評語。評語必須引用原文具體例子，指出好在哪裡、不好在哪裡。
同時請：
1. 列出 2-3 個優點
2. 列出 2-3 個具體改進建議
3. 在 annotated_text 中，用【批注：...】標記在原文相關位置後

輸出必須是有效的 JSON，不加 markdown 代碼塊。"""


def _build_essay_grade_user_prompt(req: EssayGradeRequest) -> str:
    genre_label = _GENRE_LABELS.get(req.genre, req.genre)

    schema = {
        "content": {"score": 32, "max_score": 40, "comment": "取材恰當，能緊扣主題..."},
        "expression": {"score": 30, "max_score": 40, "comment": "詞彙尚可，但句式較單一..."},
        "organization": {"score": 16, "max_score": 20, "comment": "結構完整，段落銜接自然..."},
        "total_score": 78,
        "max_score": 100,
        "percentage": 78.0,
        "strengths": ["優點一：具體引用原文說明", "優點二：具體引用原文說明"],
        "improvements": ["改進一：具體建議", "改進二：具體建議"],
        "overall_comment": "整體評語...",
        "annotated_text": "原文段落一。【批注：此處表達流暢】原文段落二。【批注：此處論據不夠充分】",
    }

    return f"""請按以下 HKDSE 評分標準批改這篇{genre_label}：

{_RUBRIC}

作文題目：{req.title or "（未提供）"}

學生作文：
---
{req.essay}
---

請輸出 JSON，格式如下（分數僅為示例，請根據實際水平給分）：
{json.dumps(schema, ensure_ascii=False, indent=2)}"""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/essay-grade")
async def grade_essay(req: EssayGradeRequest) -> dict[str, Any]:
    """批改中文作文，按 HKDSE 卷二三維度評分。"""
    try:
        system_prompt = _build_essay_grade_system_prompt()
        user_prompt = _build_essay_grade_user_prompt(req)

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)

        # Parse JSON
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result: dict[str, Any] = json.loads(cleaned)

        # Validate required fields
        for field in ("content", "expression", "organization"):
            if field not in result:
                result[field] = {"score": 0, "max_score": 40, "comment": "評分數據缺失"}

        if "total_score" not in result:
            result["total_score"] = (
                result.get("content", {}).get("score", 0)
                + result.get("expression", {}).get("score", 0)
                + result.get("organization", {}).get("score", 0)
            )
        result.setdefault("max_score", 100)
        if "percentage" not in result and result.get("max_score", 0) > 0:
            result["percentage"] = round(result["total_score"] / result["max_score"] * 100, 1)

        return result

    except Exception as exc:
        logger.error(f"HKDSE Chinese essay grading error: {exc}\n{traceback.format_exc()}")
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# F1 — Paper Generator
# ═══════════════════════════════════════════════════════════════════════════════

class GeneratePaperRequest(BaseModel):
    kb_name: str | None = None
    title: str = "HKDSE 中國語文 卷一"
    passage_type: str = "白話文"           # 白話文 | 文言文
    question_types: list[str] = ["mcq", "short_answer"]
    num_questions: int = 8
    difficulty: str = "medium"


async def _rag_retrieve(kb_name: str, query: str) -> str:
    try:
        from deeptutor.services.rag.service import RAGService
        svc = RAGService()
        result = await svc.search(query=query, kb_name=kb_name)
        return result.get("content") or result.get("answer") or ""
    except Exception as e:
        logger.warning(f"RAG failed for chinese paper-gen: {e}")
        return ""


@router.post("/generate-paper")
async def generate_paper(req: GeneratePaperRequest):
    """生成 HKDSE 卷一閱讀理解試卷（含篇章 + 題目 + 標準答案）。"""

    async def _stream():
        try:
            yield json.dumps({"type": "progress", "message": "正在從知識庫檢索相關內容..."}, ensure_ascii=False) + "\n"

            context = ""
            if req.kb_name:
                context = await _rag_retrieve(req.kb_name, req.passage_type or "閱讀理解")

            yield json.dumps({"type": "progress", "message": "正在生成閱讀篇章和試題..."}, ensure_ascii=False) + "\n"

            schema = {
                "title": req.title,
                "passage": "<閱讀篇章（文言文約300字/白話文約800字）>",
                "questions": [
                    {"id": "q1", "type": "mcq", "topic": "主旨理解", "points": 2,
                     "question": "<題目>", "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                     "answer": "A", "explanation": "<解釋>"},
                ],
            }

            passage_label = req.passage_type
            user_prompt = (
                f"請生成一份 HKDSE 中國語文科 卷一閱讀理解試卷。\n"
                f"試卷標題：{req.title}\n"
                f"篇章類型：{passage_label}\n"
                f"難度：{req.difficulty}\n"
                f"題目數量：{req.num_questions} 題\n"
                f"題型：{', '.join(req.question_types)}\n"
                f"{'參考資料：' + context[:3000] if context else ''}\n"
                f"\n要求：\n"
                f"- 生成一篇完整的閱讀篇章（白話文約800字/文言文約300字）\n"
                f"- 題目涵蓋不同能力層次：字詞理解、段落分析、主旨歸納、深層意義\n"
                f"- 每題附上標準答案和詳細解釋\n"
                f"\n請輸出 JSON：\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
            )

            system_prompt = "你是一位資深的 HKDSE 中國語文科出卷員。請生成高質素的閱讀理解試卷。輸出必須是有效的 JSON，不加 markdown 代碼塊。"

            raw = await llm_complete(user_prompt, system_prompt=system_prompt)

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            paper: dict[str, Any] = json.loads(cleaned)
            for i, q in enumerate(paper.get("questions", [])):
                q.setdefault("id", f"q{i+1}")
                q.setdefault("points", 2)
                q.setdefault("topic", "General")
                q.setdefault("explanation", "")

            yield json.dumps({"type": "done", "paper": paper}, ensure_ascii=False) + "\n"

        except Exception as e:
            logger.error(f"Chinese paper generation error: {e}\n{traceback.format_exc()}")
            yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(_stream(), media_type="application/x-ndjson")


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — Classical Chinese Assistant
# ═══════════════════════════════════════════════════════════════════════════════

class ClassicalChineseRequest(BaseModel):
    passage: str                          # 文言文段落


@router.post("/analyze-classical")
async def analyze_classical_chinese(req: ClassicalChineseRequest) -> dict[str, Any]:
    """分析文言文段落：逐句語譯、字詞注釋、理解題生成。"""
    try:
        schema = {
            "title": "<篇章題目>",
            "author": "<作者/出處>",
            "sentences": [
                {"original": "原文句一", "translation": "白話語譯", "keywords": [{"word": "重點字", "meaning": "解釋"}]},
            ],
            "comprehension_questions": [
                {"id": "q1", "question": "理解題", "answer": "答案", "explanation": "解釋"},
            ],
        }

        system_prompt = "你是一位資深的文言文教師。請對學生提供的文言文段落進行詳細分析。輸出必須是有效的 JSON，不加 markdown 代碼塊。"
        user_prompt = (
            "請分析以下文言文段落，提供：\n"
            "1. 篇章題目和作者/出處\n"
            "2. 逐句的白話語譯\n"
            "3. 每句中的重點字詞注釋（字詞 + 解釋）\n"
            "4. 3 道理解題（涵蓋內容理解和寫作手法分析）\n\n"
            f"文言文原文：\n{req.passage}\n\n"
            f"請輸出 JSON：\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result: dict[str, Any] = json.loads(cleaned)
        for i, q in enumerate(result.get("comprehension_questions", [])):
            q.setdefault("id", f"q{i+1}")
        return result

    except Exception as e:
        logger.error(f"Classical Chinese analysis error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
