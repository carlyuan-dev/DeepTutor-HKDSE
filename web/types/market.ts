// ─── Shared types for the Market Learning Loop ───────────────────────────────

export type QuestionType = "mcq" | "fill_blank" | "short_answer";
export type Difficulty = "easy" | "medium" | "hard";

// ── PaperForge ────────────────────────────────────────────────────────────────

export interface Question {
  id: string;
  type: QuestionType;
  topic: string;
  question: string;
  options?: string[];   // MCQ only
  answer: string;
  explanation: string;
  points: number;
}

export interface ExamPaper {
  title: string;
  questions: Question[];
}

// Student answers: question_id → answer string
export type StudentAnswers = Record<string, string>;

// ── ExamGrader ────────────────────────────────────────────────────────────────

export interface QuestionFeedback {
  question_id: string;
  score: number;
  max_score: number;
  is_correct: boolean;
  comment: string;
  correct_answer: string;
}

export interface GradeResult {
  results: QuestionFeedback[];
  total_score: number;
  max_score: number;
  percentage: number;
  weak_topics: string[];
  summary: string;
}

// ── FlashDeck ─────────────────────────────────────────────────────────────────

export type SMRating = "again" | "hard" | "good" | "easy";

export interface Flashcard {
  id: string;
  topic: string;
  front: string;
  back: string;
  // SM-2 state (client-side only)
  interval: number;    // days until next review
  easeFactor: number;  // 2.5 default
  repetitions: number;
}

export interface ReviewRecord {
  cardId: string;
  rating: SMRating;
  reviewedAt: number;
}

// ── localStorage keys ─────────────────────────────────────────────────────────

export const STORAGE_KEYS = {
  paper: "dtmarket_paper",
  answers: "dtmarket_answers",
  result: "dtmarket_result",
  weakTopics: "dtmarket_weak_topics",
  flashcards: "dtmarket_flashcards",
} as const;
