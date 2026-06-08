// ─── Shared types for the Market Learning Loop ───────────────────────────────

export type QuestionType = "mcq" | "fill_blank" | "short_answer" | "summary";
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
  passage?: string;
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

// ── HKDSE Chinese ─────────────────────────────────────────────────────────────

export interface DimensionScore {
  score: number;
  max_score: number;
  comment: string;
}

export interface ChineseEssayResult {
  content: DimensionScore;
  expression: DimensionScore;
  organization: DimensionScore;
  total_score: number;
  max_score: number;
  percentage: number;
  strengths: string[];
  improvements: string[];
  overall_comment: string;
  annotated_text: string;
}

export interface ChineseEssayRequest {
  title: string;
  essay: string;
  genre: "narrative" | "argumentative" | "descriptive";
}

// ── HKDSE English ─────────────────────────────────────────────────────────────

export interface EnglishEssayRequest {
  title: string;
  essay: string;
  genre: "argument" | "letter" | "report" | "article";
}

// HKDSE Paper 2 uses the Content / Language / Organisation (C/L/O) rubric,
// which is structurally different from the Chinese 內容/表達/組織 rubric.
export interface EnglishEssayResult {
  content: DimensionScore;
  language: DimensionScore;
  organisation: DimensionScore;
  total_score: number;
  max_score: number;
  percentage: number;
  strengths: string[];
  improvements: string[];
  overall_comment: string;
  annotated_essay: string;
}

export interface GenerateEnglishPaperRequest {
  kb_name?: string;
  title?: string;
  passage_type?: "informational" | "argumentative" | "narrative";
  question_types?: string[];
  num_questions?: number;
  difficulty?: string;
}

// ── HKDSE Maths ───────────────────────────────────────────────────────────────

export interface StepCheckRequest {
  question: string;
  student_steps: string[];
}

export interface StepResult {
  step_index: number;
  student_step: string;
  is_correct: boolean;
  comment: string;
  corrected_step: string;
}

export interface StepCheckResult {
  steps: StepResult[];
  first_error_index: number | null;
  overall_correct: boolean;
  full_solution: string;
  summary: string;
}

// ── localStorage keys ─────────────────────────────────────────────────────────

export const STORAGE_KEYS = {
  paper: "dtmarket_paper",
  answers: "dtmarket_answers",
  result: "dtmarket_result",
  weakTopics: "dtmarket_weak_topics",
  flashcards: "dtmarket_flashcards",
} as const;
