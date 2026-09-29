"""English integrated-skills feedback."""

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


class IntegratedSkillsRequest(BaseModel):
    stage: str = "note_making"            # note_making | summary | output
    task_type: str = "letter"             # letter | report | article
    input_texts: list[str]                # 兩篇輸入文本
    student_response: str                 # 學生的答案


@router.post("/integrated-skills")
async def integrated_skills_feedback(req: IntegratedSkillsRequest) -> dict[str, Any]:
    """為 HKDSE Paper 3 Integrated Skills 各階段提供 AI 回饋。"""
    try:
        stage_labels = {
            "note_making": "Note-making (筆記)",
            "summary": "Summary Writing (摘要)",
            "output": f"Output Text - {req.task_type} (輸出文本)",
        }
        stage_label = stage_labels.get(req.stage, req.stage)

        text1 = req.input_texts[0] if len(req.input_texts) > 0 else "(not provided)"
        text2 = req.input_texts[1] if len(req.input_texts) > 1 else "(not provided)"

        schema = {
            "stage": req.stage,
            "feedback": {"score": 3, "max_score": 5, "comment": "具體評語..."},
            "strengths": ["優點一"],
            "improvements": ["改進建議一"],
            "model_answer": "模範答案...",
        }

        system_prompt = (
            "You are an HKDSE English Paper 3 examiner. Provide detailed feedback "
            "on the student's integrated skills task. Output ONLY valid JSON."
        )

        user_prompt = (
            f"Evaluate this HKDSE Paper 3 {stage_label} response.\n\n"
            f"Task type: {req.task_type}\n\n"
            f"Input Text 1:\n{text1[:2000]}\n\n"
            f"Input Text 2:\n{text2[:2000]}\n\n"
            f"Student Response:\n{req.student_response}\n\n"
            f"Provide feedback and a model answer.\n"
            f"Return JSON:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return json.loads(cleaned)

    except Exception as e:
        logger.error(f"Integrated Skills error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
