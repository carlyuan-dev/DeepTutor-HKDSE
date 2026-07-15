# DeepTutor × HKDSE — System Optimization Report
## Advanced Features for Graduate Thesis Defense

> Version: DeepTutor v1.4.2 + Custom Market/HKDSE Module  
> Code: 9 optimizations, +12 new endpoints, ~600 lines of novel logic  
> Date: July 2026

---

## 1. Multi-Agent Ensemble Grading

**Problem**: A single LLM grading a student essay produces unstable scores — the same essay can receive different marks depending on subtle prompt variations.

**Solution**: Three agents with distinct grading personalities (strict / lenient / balanced) grade the essay in parallel. The median score is taken as the final mark.

**Implementation** (`hkdse_chinese.py`, `hkdse_english.py`):
- Three `asyncio.gather()` calls with different system prompts
- Strict persona: "Grade conservatively — award high marks only when clearly excels"
- Lenient persona: "Give the benefit of the doubt — focus on strengths"
- Balanced persona: "Weigh strengths and weaknesses evenly, following the rubric exactly"
- Final score = median of three dimension scores

**Academic significance**: 
- Eliminates single-LLM scoring instability (ensemble learning applied to LLM outputs)
- Inter-rater disagreement serves as a confidence indicator
- The three scorers' score range is a proxy for grading reliability

---

## 2. Self-Reflection Loop

**Problem**: Even with ensemble grading, the evaluation may miss subtle strengths or weaknesses in the student's work.

**Solution**: After the initial grading pass, the LLM is asked to re-examine its own scoring, considering whether any strengths or weaknesses were overlooked.

**Implementation**: 
- Phase 2 prompt after ensemble grading: "Re-examine your grading. Did you miss any strengths or weaknesses? Should the score be adjusted?"
- Output: `{score_adjusted: true/false, reflection_note: "...", revised_overall_comment: "..."}`
- If score_adjusted = true, the revised comment replaces the original

**Academic significance**:
- Implements the "Reflect" pattern from modern agent architectures
- Demonstrates awareness of LLM hallucination risks
- Provides a mechanism for self-correction

---

## 3. Scoring Confidence Annotation

**Problem**: Users have no way to know which scores are reliable and which need manual review.

**Solution**: Confidence is computed from the score range between the three ensemble agents. Smaller disagreement = higher confidence.

**Implementation**:
```
confidence = max(50, round(100 - score_range / max_score * 100))
agreement_level = "high" (≥85%) | "moderate" (65-85%) | "low" (<65%)
```
- Three-dimensional confidence (Content, Expression, Organization)
- Overall confidence = mean of three dimensions
- Human-readable interpretation: "moderate agreement — consider reviewing borderline items"

**Academic significance**:
- Transforms grading from black-box to transparent
- Defines clear thresholds for when human review is needed
- Provides a quantifiable metric for system reliability

---

## 4. Socratic Tutor — True Multi-Turn Dialogue

**Problem**: The original Socratic Tutor generated all questions in a single prompt, creating an illusion of dialogue without actual interactivity.

**Solution**: Stateful multi-turn conversation system with stuck detection and automatic remediation.

**Implementation** (`market_tools.py`, 2 new endpoints):
- `POST /socratic/start`: Creates a session with `session_id`, returns first guiding question
- `POST /socratic/respond`: Evaluates student's answer, dynamically generates next question
- Session state stored in memory: `{topic, rounds, stuck_count, history, understanding}`
- Stuck detection: keyword matching ("I don't know", "不知道") + answer length threshold (< 10 chars)
- Auto-escalation: stuck_count ≥ 2 OR rounds ≥ 5 → gives direct explanation and concludes
- Student progress tracking: correct → deeper question; partial → probe gap; wrong → hint

**Academic significance**:
- Demonstrates understanding of conversational agent design patterns
- Implements pedagogically-sound escalation strategy
- State management enables future multi-session learning tracking

---

## 5. Concept Explainer — Self-Check Verification

**Problem**: The original Concept Explainer generated an explanation but never verified whether the student actually understood it.

**Solution**: Add a verification endpoint that checks the student's answer to the self-check question and provides differentiated feedback.

**Implementation** (`market_tools.py`, 1 new endpoint):
- `POST /concept-explainer/verify`: Takes student's answer → LLM evaluates correct/partial/wrong
- Correct → praise + harder follow-up question
- Partial → acknowledge what's right, probe the gap with a hint
- Wrong → identify the specific misunderstanding, re-explain the key point

**Academic significance**:
- Forms a complete "explain → test → feedback → remediate" instructional cycle
- Differentiated feedback strategy based on accuracy level
- Aligns with mastery learning pedagogical theory

---

## 6. Mistake Notebook — Persistent Storage + SM-2 Spaced Repetition

**Problem**: The original Mistake Notebook analyzed a mistake once and discarded the result.

**Solution**: Persistent JSON storage with SM-2 algorithm for adaptive review scheduling.

**Implementation** (`market_tools.py`, 3 new endpoints):
- `POST /mistake-book/record`: Logs mistake with LLM root cause analysis + similar question generation + SM-2 initial state
- `GET /mistake-book/review`: Returns mistakes due for review (next_review ≤ now), grouped by topic
- `POST /mistake-book/update`: Updates SM-2 state after re-attempt (again=reset, hard/good/easy=extend interval)

**SM-2 Algorithm**:
```
q = quality rating (0-5)
if q < 3: interval = 1, repetitions = 0    // failed — reset
else:
    if repetitions == 0: interval = 1
    elif repetitions == 1: interval = 6
    else: interval = round(interval * ease_factor)
    repetitions += 1
ease_factor = max(1.3, ease_factor + 0.1 - (5-q) * (0.08 + (5-q) * 0.02))
// Mastered: interval ≥ 21 days → auto-remove from active review
```

**Academic significance**:
- Implements a proven cognitive science algorithm (SM-2)
- Demonstrates understanding of memory decay and spaced learning
- Adaptive scheduling personalizes review frequency per knowledge item

---

## 7. Diagnosis → Study Planner Bridge

**Problem**: Diagnostic Quiz and Study Planner were independent tools. After completing a diagnostic, the student had to manually re-enter weak topics into the planner.

**Solution**: Automatic data pipeline — diagnostic results directly drive study plan generation.

**Implementation** (`market_tools.py`, 1 new endpoint):
- `POST /diagnostic/to-plan`: Takes diagnostic profile → generates targeted remediation plan
- Automatically prioritizes weakest topics (60% of time allocation)
- Interleaves review of previously covered material
- Gradual consolidation toward exam date

**Academic significance**:
- Demonstrates system integration thinking beyond isolated tools
- Implements data-driven personalization rather than static planning
- Forms "diagnose → plan → execute → re-diagnose" learning loop

---

## 8. Mistakes → Concept Map Bridge

**Problem**: Accumulated mistakes were stored but not analyzed for cross-topic patterns.

**Solution**: Automatic knowledge graph generation from mistake data, revealing prerequisite dependencies.

**Implementation** (`market_tools.py`, 1 new endpoint):
- `POST /mistake-book/to-concept-map`: Takes topic-wise mistake counts → generates Mermaid concept map
- LLM analyzes prerequisite relationships between weak topics
- Identifies root cause topics (e.g., "Algebra Basics" causing errors in both "Quadratic Functions" and "Trigonometry")
- Output: Mermaid graph TD syntax + structural analysis + prerequisite map

**Academic significance**:
- Applies knowledge graph techniques to educational data
- Reveals hidden prerequisite gaps that simple topic counting misses
- Provides a systematic view of a student's knowledge structure

---

## 9. 5** Model Answer Generation

**Problem**: Essay grading told students what was wrong but didn't show them what excellence looks like.

**Solution**: Automatically generate a top-grade (5**) model essay on the same topic and genre.

**Implementation** (`market_tools.py`, 1 new endpoint):
- `POST /essay/model-answer`: Takes topic + genre + optional student essay → generates ~1000-word model answer
- Includes: scoring breakdown per dimension, key features of top-tier writing, comparison notes with student's essay, immediately applicable writing techniques
- Supports both Chinese (内容/表达/组织) and English (C/L/O) rubrics

**Academic significance**:
- Transforms negative feedback ("here's what's wrong") into positive guidance ("here's how to do it right")
- Aligns with exemplar-based learning theory
- Each learnable technique is concrete and actionable

---

## Implementation Statistics

| Metric | Value |
|:---|:---|
| New API endpoints added | 12 |
| Modified endpoints | 2 (Chinese + English essay-grade) |
| Total new code lines | ~600 |
| Files modified | 3 (`market_tools.py`, `hkdse_chinese.py`, `hkdse_english.py`) |
| Algorithms implemented | SM-2, Ensemble Median, Confidence Computation, Stuck Detection |
| Key libraries leveraged | `asyncio.gather` (parallel LLM calls), `statistics.median`, `hashlib` (session IDs) |

---

## Innovation Summary for Thesis Defense

**Core argument**: This project goes beyond "wrapping ChatGPT with a UI" in three ways:

1. **Domain-specific rubric engineering**: HKDSE official marking criteria are structurally embedded in prompts, producing grading that aligns with the actual exam — not generic "good/bad" feedback.

2. **Multi-agent reliability**: Ensemble grading with inter-rater confidence eliminates the single-LLM randomness problem. Each score is accompanied by a confidence level and agreement analysis.

3. **Tool ecosystem with data pipelines**: Unlike isolated AI tools, these optimizations create cross-tool data flows — diagnostic results drive study plans, mistake patterns generate concept maps, and grading reflections improve future assessments. The system behaves as a coherent learning platform, not a collection of disconnected prompts.
