import type { GradeResult, LearningLoopEntry, LearningLoopPractice } from "@/types/market";
import { STORAGE_KEYS } from "@/types/market";

export const LEARNING_LOOP_CHANGE = "learning-loop-change";
export const LEARNING_LOOP_RESULT_CHANGE = "learning-loop-result-change";
export const RESTART_MESSAGE = "Practice context is missing or has changed. Please start a new practice from its subject page.";

function validEntry(subject: string, entry: string): boolean {
  return (entry === "/market/paper-forge" && !!subject.trim())
    || (entry === "/market/hkdse/chinese/paper-generator" && subject === "chinese")
    || (entry === "/market/hkdse/english/paper-generator" && subject === "english");
}

// One submission envelope avoids mixing paper/answers/context from separate keys.
// Legacy global keys are deliberately neither inferred nor used as fallback.
export function readPractice(): LearningLoopPractice | null {
  try {
    const practice = JSON.parse(localStorage.getItem(STORAGE_KEYS.learningLoop) || "null");
    if (!practice || typeof practice.id !== "string" || !practice.id
      || typeof practice.subject !== "string" || typeof practice.entry !== "string"
      || !validEntry(practice.subject, practice.entry) || typeof practice.kb_name !== "string"
      || !practice.paper || !Array.isArray(practice.paper.questions)
      || !practice.answers || typeof practice.answers !== "object" || Array.isArray(practice.answers)
      || !Array.isArray(practice.weak_topics) || !practice.weak_topics.every((t: unknown) => typeof t === "string")) return null;
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEYS.learningLoopResult + practice.id) || "null");
    const result = saved?.practice_id === practice.id && Array.isArray(saved.result?.weak_topics)
      && saved.result.weak_topics.every((t: unknown) => typeof t === "string") ? saved.result : undefined;
    return { ...practice, result, weak_topics: result?.weak_topics ?? practice.weak_topics };
  } catch {
    return null;
  }
}

export function isCurrentPractice(id: string): boolean {
  return readPractice()?.id === id;
}

export function savePractice(practice: LearningLoopPractice): void {
  localStorage.setItem(STORAGE_KEYS.learningLoop, JSON.stringify({ ...practice, weak_topics: [], result: undefined }));
  window.dispatchEvent(new Event(LEARNING_LOOP_CHANGE));
}

export function savePracticeResult(id: string, result: GradeResult): boolean {
  if (!isCurrentPractice(id)) return false;
  // localStorage has no cross-tab CAS. Never rewrite the current envelope here:
  // even an interleaving after this check can only write the OLD id's result key.
  localStorage.setItem(STORAGE_KEYS.learningLoopResult + id, JSON.stringify({ practice_id: id, result }));
  if (!isCurrentPractice(id)) return false;
  window.dispatchEvent(new Event(LEARNING_LOOP_RESULT_CHANGE));
  return isCurrentPractice(id);
}

export function readRetake(entry: LearningLoopEntry): LearningLoopPractice | null {
  const id = new URLSearchParams(window.location.search).get("practice");
  if (!id) return null;
  const practice = readPractice();
  if (!practice || practice.id !== id || practice.entry !== entry) throw new Error(RESTART_MESSAGE);
  return practice;
}

export function retakeUrl(practice: LearningLoopPractice): string {
  return `${practice.entry}?practice=${encodeURIComponent(practice.id)}`;
}
