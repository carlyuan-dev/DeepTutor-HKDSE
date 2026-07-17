import { apiUrl } from "@/lib/api";
import type {
  ChineseEssayRequest,
  ChineseEssayResult,
  EnglishEssayRequest,
  EnglishEssayResult,
  ExamPaper,
  Flashcard,
  GenerateEnglishPaperRequest,
  GradeResult,
  OralFeedbackResult,
  OralMessage,
  OralTopicResponse,
  OralTurnRequest,
  Question,
  SMRating,
  StepCheckRequest,
  StepCheckResult,
  StudentAnswers,
} from "@/types/market";

// ── PaperForge ────────────────────────────────────────────────────────────────

export interface GeneratePaperOptions {
  kb_name?: string;
  title?: string;
  question_types?: string[];
  num_questions?: number;
  difficulty?: string;
  topic_focus?: string;
}

/**
 * Stream paper generation. Calls onProgress for each progress event,
 * resolves with the finished ExamPaper on "done".
 */
export async function generatePaper(
  options: GeneratePaperOptions,
  onProgress: (message: string) => void
): Promise<ExamPaper> {
  const res = await fetch(apiUrl("/api/v1/paper-forge/generate"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Server error ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "progress") {
        onProgress(event.message);
      } else if (event.type === "done") {
        return event.paper as ExamPaper;
      } else if (event.type === "error") {
        throw new Error(event.message);
      }
    }
  }

  throw new Error("Stream ended without a paper");
}

// ── ExamGrader ────────────────────────────────────────────────────────────────

export async function gradeSubmission(
  questions: Question[],
  student_answers: StudentAnswers
): Promise<GradeResult> {
  const res = await fetch(apiUrl("/api/v1/exam-grader/grade"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ questions, student_answers }),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data as GradeResult;
}

// ── FlashDeck ─────────────────────────────────────────────────────────────────

export async function generateCards(
  topics: string[],
  kb_name?: string,
  num_cards = 15
): Promise<Flashcard[]> {
  const res = await fetch(apiUrl("/api/v1/flash-deck/generate"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topics, kb_name, num_cards }),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);

  return (data.cards as Omit<Flashcard, "interval" | "easeFactor" | "repetitions">[]).map(
    (c) => ({ ...c, interval: 1, easeFactor: 2.5, repetitions: 0 })
  );
}

// ── SM-2 algorithm (client-side) ──────────────────────────────────────────────

/**
 * Update a flashcard's scheduling state based on the user's rating.
 * Returns an updated copy of the card.
 */
export function applyRating(card: Flashcard, rating: SMRating): Flashcard {
  const ratingMap: Record<SMRating, number> = { again: 0, hard: 3, good: 4, easy: 5 };
  const q = ratingMap[rating];

  let { interval, easeFactor, repetitions } = card;

  if (q < 3) {
    // Failed — reset
    repetitions = 0;
    interval = 1;
  } else {
    if (repetitions === 0) interval = 1;
    else if (repetitions === 1) interval = 6;
    else interval = Math.round(interval * easeFactor);
    repetitions += 1;
  }

  easeFactor = Math.max(1.3, easeFactor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02));

  return { ...card, interval, easeFactor, repetitions };
}

// ── HKDSE Chinese ─────────────────────────────────────────────────────────────

export async function gradeChineseEssay(
  req: ChineseEssayRequest
): Promise<ChineseEssayResult> {
  const res = await fetch(apiUrl("/api/v1/hkdse/chinese/essay-grade"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data as ChineseEssayResult;
}

// ── HKDSE English ─────────────────────────────────────────────────────────────

export async function gradeEnglishEssay(
  req: EnglishEssayRequest
): Promise<EnglishEssayResult> {
  const res = await fetch(apiUrl("/api/v1/hkdse/english/essay-grade"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data as EnglishEssayResult;
}

export async function generateEnglishPaper(
  options: GenerateEnglishPaperRequest,
  onProgress: (message: string) => void
): Promise<ExamPaper> {
  const res = await fetch(apiUrl("/api/v1/hkdse/english/generate-paper"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
  if (!res.ok || !res.body) throw new Error(`Server error ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "progress") onProgress(event.message);
      else if (event.type === "done") return event.paper as ExamPaper;
      else if (event.type === "error") throw new Error(event.message);
    }
  }
  throw new Error("Stream ended without a paper");
}

// ── HKDSE English Oral Practice ────────────────────────────────────────────

export async function getRandomOralTopic(
  category: string
): Promise<OralTopicResponse> {
  const res = await fetch(apiUrl("/api/v1/hkdse/english/oral-topics"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category }),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data as OralTopicResponse;
}

export type OralTurnCallbacks = {
  onChunk: (text: string) => void;
  onTurnEnd: (event: {
    speaker: string;
    content: string;
    next_speaker: string;
    continues: boolean;
    phase: string | null;
  }) => void;
  onError: (message: string) => void;
};

export async function takeOralTurn(
  req: OralTurnRequest,
  callbacks: OralTurnCallbacks,
  options?: { signal?: AbortSignal }
): Promise<void> {
  try {
    const res = await fetch(apiUrl("/api/v1/hkdse/english/oral-turn"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal: options?.signal,
    });

    if (!res.ok || !res.body) {
      callbacks.onError(`Server error ${res.status}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);

        if (event.type === "chunk") {
          callbacks.onChunk(event.content);
        } else if (event.type === "turn_end") {
          callbacks.onTurnEnd({
            speaker: event.speaker,
            content: event.content,
            next_speaker: event.next_speaker,
            continues: event.continues,
            phase: event.phase ?? null,
          });
        } else if (event.type === "error") {
          callbacks.onError(event.message);
          return;
        }
      }
    }
  } catch (e: unknown) {
    if (
      options?.signal?.aborted
      || (e instanceof DOMException && e.name === "AbortError")
      || (e instanceof Error && e.name === "AbortError")
    ) return;
    callbacks.onError(e instanceof Error ? e.message : "Stream parse failed");
  }
}

export async function getOralFeedback(
  req: OralTurnRequest
): Promise<OralFeedbackResult> {
  const res = await fetch(apiUrl("/api/v1/hkdse/english/oral-feedback"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data as OralFeedbackResult;
}

// ── HKDSE Maths ───────────────────────────────────────────────────────────────

export async function checkMathSteps(
  req: StepCheckRequest
): Promise<StepCheckResult> {
  const res = await fetch(apiUrl("/api/v1/hkdse/maths/step-check"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data as StepCheckResult;
}

// ── HKDSE Chinese Paper Generator ─────────────────────────────────────────────

export async function generateChinesePaper(
  options: {
    kb_name?: string;
    title?: string;
    passage_type?: string;
    question_types?: string[];
    num_questions?: number;
    difficulty?: string;
  },
  onProgress: (message: string) => void
): Promise<ExamPaper> {
  const res = await fetch(apiUrl("/api/v1/hkdse/chinese/generate-paper"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
  if (!res.ok || !res.body) throw new Error(`Server error ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "progress") onProgress(event.message);
      else if (event.type === "done") return event.paper as ExamPaper;
      else if (event.type === "error") throw new Error(event.message);
    }
  }
  throw new Error("Stream ended without a paper");
}
