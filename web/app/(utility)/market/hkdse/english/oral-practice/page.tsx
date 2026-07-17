"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Globe,
  Lock,
  Mic,
  SkipForward,
  Square,
  Volume2,
  type LucideIcon,
} from "lucide-react";
import { getRandomOralTopic, takeOralTurn, getOralFeedback } from "@/lib/market-api";
import type { OralFeedbackResult, OralMessage, OralTopicResponse, OralTopic, OralVoiceMetadata } from "@/types/market";

type Stage = "config" | "reading" | "discussion" | "feedback" | "error";
type PracticeMode = "voice" | "text";
type AiSpeaker = "candidate_a" | "candidate_b" | "candidate_c";
type AgendaIntent = "open_agenda_item" | "respond_to_user_opened_agenda" | "respond_and_add" | "close_agenda_item" | "free_extension";
type AgendaStance = "support_extend" | "soft_challenge" | "balance_both_sides" | "new_angle" | "summarize_transition";
type UserAgendaSignal = {
  agendaIndex: number;
  openedByUser: boolean;
};
type AiTurnPlan = {
  speaker: AiSpeaker;
  agendaIndex: number;
  agendaItem: string;
  previousAgendaItem?: string;
  agendaIntent: AgendaIntent;
  agendaStance: AgendaStance;
};
type PreparedAiTurn = AiTurnPlan & {
  content: string;
  basisText?: string;
};

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { resultIndex: number; results: SpeechRecognitionResultList }) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  }
}

const TOPICS: { key: OralTopic; label: string; icon: LucideIcon }[] = [
  { key: "education", label: "Education & Learning", icon: Globe },
  { key: "technology", label: "Technology & Society", icon: Globe },
  { key: "environment", label: "Environment & Conservation", icon: Globe },
  { key: "social_issues", label: "Social Issues", icon: Globe },
];

const AI_TURN_BUFFER_MS = 1100;
const AGENDA_TRANSITION_BUFFER_MS = 2200;
const PART_A_DURATION_SECONDS = 485;
const PART_B_DURATION_SECONDS = 65;
const AI_AUTO_START_AFTER_SECONDS = 6;
const SPECULATIVE_USER_PREFETCH_MIN_WORDS = 8;
const SPEECH_STOP_FLUSH_MS = 180;
const AI_CAPTION_WORD_INTERVAL_MS = 115;
const FIRST_AI_TURN_BUFFER_MS = AI_AUTO_START_AFTER_SECONDS * 1000;
const AI_SPEAKERS: AiSpeaker[] = ["candidate_a", "candidate_b", "candidate_c"];

const SPEAKER_COLORS: Record<string, string> = {
  candidate_a: "border-blue-500/30 bg-blue-500/10 text-blue-400",
  candidate_b: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  candidate_c: "border-purple-500/30 bg-purple-500/10 text-purple-400",
  candidate_d: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  examiner: "border-rose-500/30 bg-rose-500/10 text-rose-400",
};

const SPEAKER_LABELS: Record<string, string> = {
  candidate_a: "Candidate A",
  candidate_b: "Candidate B",
  candidate_c: "Candidate C",
  candidate_d: "You",
  examiner: "Examiner",
};

function shuffledAiQueue(previousLast?: AiSpeaker | null): AiSpeaker[] {
  const queue = [...AI_SPEAKERS];
  for (let i = queue.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [queue[i], queue[j]] = [queue[j], queue[i]];
  }
  if (previousLast && queue[0] === previousLast && queue.length > 1) {
    [queue[0], queue[1]] = [queue[1], queue[0]];
  }
  return queue;
}

function choosePartBQuestion(topic: OralTopicResponse | null): string {
  const questions = topic?.part_b_questions?.filter(Boolean) ?? [];
  if (questions.length === 0) return "What are your personal views on this topic?";
  return questions[Math.floor(Math.random() * questions.length)];
}

function weightedPick<T extends string>(items: { value: T; weight: number }[]): T {
  const total = items.reduce((sum, item) => sum + item.weight, 0);
  let cursor = Math.random() * total;
  for (const item of items) {
    cursor -= item.weight;
    if (cursor <= 0) return item.value;
  }
  return items[items.length - 1].value;
}

function chooseAgendaStance(speaker: AiSpeaker, intent: AgendaIntent): AgendaStance {
  if (intent === "close_agenda_item") return "summarize_transition";
  if (intent === "open_agenda_item" || intent === "respond_to_user_opened_agenda") {
    return weightedPick<AgendaStance>([
      { value: "new_angle", weight: 45 },
      { value: "balance_both_sides", weight: 35 },
      { value: "support_extend", weight: 20 },
    ]);
  }
  const profiles: Record<AiSpeaker, { value: AgendaStance; weight: number }[]> = {
    candidate_a: [
      { value: "new_angle", weight: 35 },
      { value: "balance_both_sides", weight: 30 },
      { value: "soft_challenge", weight: 20 },
      { value: "support_extend", weight: 15 },
    ],
    candidate_b: [
      { value: "support_extend", weight: 35 },
      { value: "balance_both_sides", weight: 30 },
      { value: "new_angle", weight: 20 },
      { value: "soft_challenge", weight: 15 },
    ],
    candidate_c: [
      { value: "soft_challenge", weight: 30 },
      { value: "new_angle", weight: 30 },
      { value: "support_extend", weight: 25 },
      { value: "balance_both_sides", weight: 15 },
    ],
  };
  return weightedPick(profiles[speaker]);
}

function normalizeForAgendaMatch(text: string): string[] {
  const stopWords = new Set([
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "about",
    "what", "why", "how", "whether", "should", "could", "would", "is", "are", "be",
    "do", "does", "did", "we", "our", "their", "this", "that", "these", "those",
  ]);
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 2 && !stopWords.has(word));
}

function findBestAgendaMatch(text: string, agendaItems: string[]) {
  const normalizedText = text.toLowerCase();
  const userWords = new Set(normalizeForAgendaMatch(text));
  let bestIndex = -1;
  let bestScore = 0;

  agendaItems.forEach((item, index) => {
    const itemWords = normalizeForAgendaMatch(item);
    const overlap = itemWords.filter((word) => userWords.has(word)).length;
    const phraseHit = normalizedText.includes(item.toLowerCase()) ? 2 : 0;
    const score = overlap + phraseHit;
    if (score > bestScore) {
      bestIndex = index;
      bestScore = score;
    }
  });

  return { bestIndex, bestScore };
}

function detectUserAgendaSignal(
  text: string,
  agendaItems: string[],
  currentAgendaIndex: number,
  hasAiSpoken: boolean,
): UserAgendaSignal | null {
  if (agendaItems.length === 0) return null;
  const transitionIntent = /\b(move on|next point|next topic|another point|now talk about|now discuss|let'?s discuss|let'?s talk about|covered this|talk about)\b/i
    .test(text);
  const { bestIndex, bestScore } = findBestAgendaMatch(text, agendaItems);

  if (bestIndex >= currentAgendaIndex && bestScore >= 2) {
    return { agendaIndex: bestIndex, openedByUser: true };
  }

  if (!hasAiSpoken && bestIndex <= currentAgendaIndex && bestScore >= 1) {
    return { agendaIndex: currentAgendaIndex, openedByUser: true };
  }

  if (bestIndex > currentAgendaIndex && transitionIntent) {
    return { agendaIndex: bestIndex, openedByUser: true };
  }

  if (transitionIntent && currentAgendaIndex + 1 < agendaItems.length) {
    return { agendaIndex: currentAgendaIndex + 1, openedByUser: true };
  }

  return null;
}

function queueStartingWith(firstSpeaker: AiSpeaker, previousLast?: AiSpeaker | null): AiSpeaker[] {
  const rest = shuffledAiQueue(previousLast).filter((speaker) => speaker !== firstSpeaker);
  return [firstSpeaker, ...rest];
}

function transcriptLooksCompatible(basis: string, finalText: string): boolean {
  const basisWords = new Set(normalizeForAgendaMatch(basis));
  const finalWords = new Set(normalizeForAgendaMatch(finalText));
  if (basisWords.size === 0) return true;
  let overlap = 0;
  basisWords.forEach((word) => {
    if (finalWords.has(word)) overlap += 1;
  });
  return overlap / basisWords.size >= 0.4;
}

function scoreColor(score: number, max: number) {
  const pct = (score / max) * 100;
  return pct >= 80 ? "text-emerald-400" : pct >= 60 ? "text-yellow-400" : "text-red-400";
}

// ── Config Stage ─────────────────────────────────────────────────────────────

function ConfigStage({
  topic,
  loading,
  speechSupported,
  onSelectTopic,
  onStart,
}: {
  topic: OralTopic | null;
  loading: boolean;
  speechSupported: boolean;
  onSelectTopic: (t: OralTopic) => void;
  onStart: () => void;
}) {
  return (
    <div className="max-w-xl space-y-6">
      <p className="text-sm text-[var(--muted-foreground)]">
        Select a discussion topic category. We will randomly pick a real
        HKDSE Paper 4 discussion task for you to practice with.
      </p>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--muted-foreground)]">
          Category
        </label>
        <div className="grid grid-cols-2 gap-2">
          {TOPICS.map((t) => (
            <button
              key={t.key}
              onClick={() => onSelectTopic(t.key)}
              className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm transition-colors ${
                topic === t.key
                  ? "border-sky-500/50 bg-sky-500/10 text-sky-400"
                  : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              <t.icon size={16} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--muted-foreground)]">
          Practice Mode
        </label>
        <div className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm ${
          speechSupported
            ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400"
            : "border-yellow-500/30 bg-yellow-500/10 text-yellow-400"
        }`}>
          <Mic size={16} />
          {speechSupported ? "Voice Practice" : "Voice Practice Unavailable"}
        </div>
        {!speechSupported && (
          <p className="text-xs text-yellow-400">
            Browser speech recognition is required for this module. Please use a supported browser.
          </p>
        )}
      </div>

      <button
        onClick={onStart}
        disabled={!topic || loading || !speechSupported}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-sky-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        {loading ? "Selecting topic..." : "Start Practice"}
      </button>
    </div>
  );
}

// ── Reading Stage (10-min preparation) ──────────────────────────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function ReadingStage({
  topic,
  onBegin,
}: {
  topic: OralTopicResponse;
  onBegin: () => void;
}) {
  const [timeLeft, setTimeLeft] = useState(600); // 10 min
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          setExpired(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const handleSkip = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    onBegin();
  };

  const timerColor =
    timeLeft > 120
      ? "text-emerald-400"
      : timeLeft > 30
        ? "text-yellow-400"
        : "text-red-400";

  return (
    <div className="max-w-2xl space-y-6">
      {/* Timer bar */}
      <div className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
        <div>
          <p className="text-xs text-[var(--muted-foreground)]">Preparation Time</p>
          <p className={`mt-1 text-2xl font-bold tabular-nums ${timerColor}`}>
            {formatTime(timeLeft)}
          </p>
        </div>
        <button
          onClick={handleSkip}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-4 py-2 text-sm text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
        >
          <SkipForward size={14} />
          {expired ? "Start Discussion" : "Skip"}
        </button>
      </div>

      {/* Topic card */}
      <div className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-5">
        <span className="rounded-md border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-400">
          {topic.category}
        </span>
        <h2 className="mt-3 text-lg font-semibold text-[var(--foreground)]">
          {topic.topic}
        </h2>

        {topic.article && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-[var(--muted-foreground)]">
              Background
            </p>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--foreground)]">
              {topic.article}
            </p>
          </div>
        )}

        {topic.discussion_task && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-[var(--muted-foreground)]">
              Discussion Task
            </p>
            <p className="text-sm leading-relaxed text-[var(--foreground)]">
              {topic.discussion_task}
            </p>
          </div>
        )}

        {topic.guiding_questions.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-[var(--muted-foreground)]">
              You may want to talk about
            </p>
            <ul className="space-y-1">
              {topic.guiding_questions.map((q, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-sm text-[var(--muted-foreground)]"
                >
                  <span className="mt-0.5 text-sky-400">•</span>
                  {q}
                </li>
              ))}
            </ul>
          </div>
        )}

        {topic.part_b_questions.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-[var(--muted-foreground)]">
              Part B Individual Response Questions
            </p>
            <ul className="space-y-1">
              {topic.part_b_questions.map((q, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-sm text-[var(--muted-foreground)]"
                >
                  <span className="mt-0.5 text-rose-400">{i + 1}.</span>
                  {q}
                </li>
              ))}
            </ul>
          </div>
        )}

        <button
          onClick={handleSkip}
          className="mt-6 w-full rounded-lg bg-sky-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          {expired ? "Start Discussion" : "Skip Preparation & Start Discussion"}
        </button>
      </div>
    </div>
  );
}

// ── Discussion Stage ─────────────────────────────────────────────────────────

function DiscussionStage({
  messages,
  streamingText,
  isAiSpeaking,
  isScoring,
  isAiBuffering,
  pendingAiSpeaker,
  agendaLabel,
  partATimeLeft,
  partBTimeLeft,
  isListening,
  interimTranscript,
  speechSupported,
  phase,
  onSkipPartA,
  onStartVoice,
  onStopVoice,
}: {
  messages: OralMessage[];
  streamingText: string;
  isAiSpeaking: boolean;
  isScoring: boolean;
  isAiBuffering: boolean;
  pendingAiSpeaker: AiSpeaker | null;
  agendaLabel: string;
  partATimeLeft: number;
  partBTimeLeft: number;
  isListening: boolean;
  interimTranscript: string;
  speechSupported: boolean;
  phase: string;
  onSkipPartA: () => void;
  onStartVoice: () => void;
  onStopVoice: () => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const activityLabel = isScoring
    ? "Scoring"
    : isAiBuffering && pendingAiSpeaker
      ? "Get ready to speak"
      : "AI responding";
  const timerLabel = phase === "individual_response" ? "Part B" : "Part A";
  const timerValue = phase === "individual_response" ? partBTimeLeft : partATimeLeft;

  return (
    <div className="flex flex-1 flex-col">
      {phase === "discussion" && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-3">
          <div className="min-w-0 px-4 text-center">
            <p className="truncate text-xs text-[var(--muted-foreground)]">{agendaLabel}</p>
          </div>
          <button
            onClick={onSkipPartA}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-2 text-xs text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            <SkipForward size={13} />
            Skip to Part B
          </button>
        </div>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto">
        {messages.map((msg, i) => {
          const isUser = msg.speaker === "candidate_d";
          const colorClass = SPEAKER_COLORS[msg.speaker] ?? "";
          const label = SPEAKER_LABELS[msg.speaker] ?? msg.speaker;
          return (
            <div key={i} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-xl border p-4 ${
                isUser
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-[var(--border)] bg-[var(--secondary)]"
              }`}>
                <div className="mb-1 flex items-center gap-2">
                  <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${colorClass}`}>
                    {label}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-[var(--foreground)]">{msg.content}</p>
              </div>
            </div>
          );
        })}

        {streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="text-sm leading-relaxed text-[var(--foreground)]">
                {streamingText}
                <span className="ml-0.5 inline-flex h-4 w-1.5 animate-pulse rounded-full bg-sky-500" />
              </p>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="sticky bottom-0 border-t border-[var(--border)] bg-[var(--background)] p-4">
        <div className="space-y-3">
          {speechSupported ? (
            <div className="flex items-center gap-3">
              <button
                onClick={isListening ? onStopVoice : onStartVoice}
                disabled={isScoring}
                className={`flex h-12 w-12 items-center justify-center rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40 ${
                  isListening ? "bg-red-500" : "bg-emerald-500"
                }`}
                title={isListening ? "Stop speaking" : "Speak"}
              >
                {isListening ? <Square size={17} /> : <Mic size={18} />}
              </button>
              <div className="min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-4 py-3">
                <p className="truncate text-sm text-[var(--foreground)]">
                  {isListening
                    ? "Listening..."
                    : "Press Speak to answer. Press Stop when finished."}
                </p>
              </div>
              <div className="min-w-[72px] rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-right">
                <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]/60">{timerLabel}</p>
                <p className="mt-0.5 text-base font-semibold tabular-nums text-[var(--foreground)]">
                  {formatTime(timerValue)}
                </p>
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3">
              <p className="text-sm text-yellow-400">
                Voice recognition is unavailable in this browser.
              </p>
            </div>
          )}
          {isListening && (
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-emerald-400/80">Your speech</p>
              <p className="min-h-5 whitespace-pre-wrap text-sm leading-relaxed text-[var(--foreground)]">
                {interimTranscript || "Listening for your voice..."}
              </p>
            </div>
          )}
        </div>
        <div className="mt-2 flex items-center justify-end text-[10px] text-[var(--muted-foreground)]/50">
          {(isAiSpeaking || isScoring || isAiBuffering) && (
            <span className="flex items-center gap-1">
              {isAiSpeaking && !isScoring ? <Volume2 size={12} /> : <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500" />}
              {activityLabel}
              {isScoring && (
                <span className="inline-flex w-4 justify-start">
                  <span className="animate-pulse">...</span>
                </span>
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Feedback Stage ───────────────────────────────────────────────────────────

function FeedbackStage({
  result,
  onNewPractice,
}: {
  result: OralFeedbackResult;
  onNewPractice: () => void;
}) {
  const pronunciationLocked = true;
  const scoredDimensions = [result.communication, result.language, result.ideas_organisation];
  const displayScore = scoredDimensions.reduce((sum, dim) => sum + (dim?.score ?? 0), 0);
  const displayMax = scoredDimensions.reduce((sum, dim) => sum + (dim?.max_score ?? 7), 0);
  const pct = displayMax > 0 ? Math.round((displayScore / displayMax) * 1000) / 10 : result.percentage;
  const totalColor = pct >= 80 ? "text-emerald-400" : pct >= 60 ? "text-yellow-400" : "text-red-400";
  const totalBg = pct >= 80
    ? "bg-emerald-500/10 border-emerald-500/30"
    : pct >= 60
      ? "bg-yellow-500/10 border-yellow-500/30"
      : "bg-red-500/10 border-red-500/30";

  const dimensions = [
    { key: "communication", label: "Communication Strategies", data: result.communication, locked: false },
    { key: "language", label: "Language", data: result.language, locked: false },
    { key: "ideas_organisation", label: "Ideas & Organisation", data: result.ideas_organisation, locked: false },
    { key: "pronunciation", label: "Pronunciation & Delivery", data: result.pronunciation_delivery, locked: pronunciationLocked },
  ];

  return (
    <div className="max-w-2xl space-y-6">
      <div className={`rounded-xl border p-6 ${totalBg}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-[var(--muted-foreground)]">
              Transcript-based Score
            </p>
            <p className={`mt-1 text-4xl font-bold ${totalColor}`}>
              {displayScore}
              <span className="text-xl font-normal text-[var(--muted-foreground)]">/{displayMax}</span>
            </p>
            <p className={`mt-0.5 text-sm font-medium ${totalColor}`}>{pct}%</p>
          </div>
          <div className="text-right text-xs text-[var(--muted-foreground)]">
            <p>Communication · Language · Ideas</p>
            <p className="mt-1">
              Pronunciation is not scored yet
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {dimensions.map((dim) => {
          const s = dim.data as unknown as { score: number; max_score: number };
          const scoreVal = s?.score ?? 0;
          const maxVal = s?.max_score ?? 7;
          const comment = "comment" in (dim.data as object)
            ? (dim.data as unknown as { comment: string }).comment ?? ""
            : "";

          return (
            <div key={dim.key} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4 text-center">
              <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]/60">{dim.label}</p>
              <p className={`mt-2 text-2xl font-bold ${dim.locked ? "text-[var(--muted-foreground)]/40" : scoreColor(scoreVal, maxVal)}`}>
                {dim.locked ? (
                  <span className="inline-flex items-center gap-1">
                    <Lock size={14} />
                    <span>0<span className="text-sm font-normal text-[var(--muted-foreground)]">/{maxVal}</span></span>
                  </span>
                ) : (
                  <>{scoreVal}<span className="text-sm font-normal text-[var(--muted-foreground)]">/{maxVal}</span></>
                )}
              </p>
              {!dim.locked && comment && (
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">{comment}</p>
              )}
              {dim.locked && (
                <p className="mt-1 text-[10px] leading-relaxed text-[var(--muted-foreground)]/50">
                  {comment || "Audio-level pronunciation analysis is not available yet."}
                </p>
              )}
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <p className="mb-2 text-xs font-medium text-emerald-400">Strengths</p>
          <ul className="space-y-1.5">{result.strengths.map((s, i) => <li key={i} className="text-xs leading-relaxed text-[var(--foreground)]">{s}</li>)}</ul>
        </div>
        <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
          <p className="mb-2 text-xs font-medium text-yellow-400">Improvements</p>
          <ul className="space-y-1.5">{result.improvements.map((s, i) => <li key={i} className="text-xs leading-relaxed text-[var(--foreground)]">{s}</li>)}</ul>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">Overall Comment</p>
        <p className="text-sm leading-relaxed text-[var(--foreground)]">{result.overall_comment}</p>
      </div>

      {result.model_excerpt && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">Model Discussion</p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--foreground)]">{result.model_excerpt}</p>
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button onClick={onNewPractice} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]">New Practice</button>
        <Link href="/market/hkdse/english" className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]">Back to English</Link>
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function OralPracticePage() {
  const [stage, setStage] = useState<Stage>("config");
  const [category, setCategory] = useState<OralTopic | null>(null);
  const [mode, setMode] = useState<PracticeMode>("voice");
  const [speechSupported, setSpeechSupported] = useState(false);
  const [topic, setTopic] = useState<OralTopicResponse | null>(null);
  const [topicLoading, setTopicLoading] = useState(false);
  const [messages, setMessages] = useState<OralMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isAiBuffering, setIsAiBuffering] = useState(false);
  const [pendingAiSpeaker, setPendingAiSpeaker] = useState<AiSpeaker | null>(null);
  const [agendaIndex, setAgendaIndex] = useState(0);
  const [partATimeLeft, setPartATimeLeft] = useState(PART_A_DURATION_SECONDS);
  const [partBTimeLeft, setPartBTimeLeft] = useState(PART_B_DURATION_SECONDS);
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [userRounds, setUserRounds] = useState(0);
  const [phase, setPhase] = useState<"discussion" | "individual_response">("discussion");
  const [result, setResult] = useState<OralFeedbackResult | null>(null);
  const [error, setError] = useState("");
  const [isScoring, setIsScoring] = useState(false);

  const streamingRef = useRef("");
  const messagesRef = useRef<OralMessage[]>([]);
  const topicIdRef = useRef("");
  const phaseRef = useRef<"discussion" | "individual_response">("discussion");
  const feedbackInFlightRef = useRef(false);
  const modeRef = useRef<PracticeMode>("voice");
  const topicRef = useRef<OralTopicResponse | null>(null);
  const agendaIndexRef = useRef(0);
  const aiQueueRef = useRef<AiSpeaker[]>([]);
  const previousAgendaLastAiRef = useRef<AiSpeaker | null>(null);
  const agendaOpenedByUserRef = useRef<number | null>(null);
  const recentlyClosedAgendaIndexRef = useRef<number | null>(null);
  const forceAdvanceAfterBufferedReplyRef = useRef<number | null>(null);
  const pendingAiSpeakerRef = useRef<AiSpeaker | null>(null);
  const aiBufferTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const partATimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const partBTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const aiCaptionTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const aiCaptionRunIdRef = useRef(0);
  const partBStartedRef = useRef(false);
  const activeAiTurnAbortRef = useRef<AbortController | null>(null);
  const activeAiTurnIdRef = useRef(0);
  const preparedAiTurnRef = useRef<PreparedAiTurn | null>(null);
  const prefetchAbortRef = useRef<AbortController | null>(null);
  const speculativeUserPrefetchKeyRef = useRef<string | null>(null);
  const partBQuestionRef = useRef("");
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const isListeningRef = useRef(false);
  const finalTranscriptRef = useRef("");
  const finalTranscriptSegmentsRef = useRef<string[]>([]);
  const interimTranscriptRef = useRef("");
  const voiceStartedAtRef = useRef(0);
  const interruptedAiRef = useRef(false);
  const interruptRequestedRef = useRef(false);
  const ttsResolveRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    topicRef.current = topic;
  }, [topic]);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    isListeningRef.current = isListening;
  }, [isListening]);

  useEffect(() => {
    const supported = typeof window !== "undefined"
      && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition)
      && "speechSynthesis" in window;
    setSpeechSupported(supported);
    return () => {
      if (aiBufferTimerRef.current) {
        clearTimeout(aiBufferTimerRef.current);
      }
      clearPartATimer();
      clearPartBTimer();
      clearAiCaption();
      activeAiTurnAbortRef.current?.abort();
      recognitionRef.current?.abort();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const cancelAiSpeech = () => {
    clearAiCaption();
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    ttsResolveRef.current?.();
    ttsResolveRef.current = null;
  };

  const clearAiCaption = () => {
    aiCaptionRunIdRef.current += 1;
    if (aiCaptionTimerRef.current) {
      clearInterval(aiCaptionTimerRef.current);
      aiCaptionTimerRef.current = null;
    }
  };

  const clearAiBuffer = () => {
    if (aiBufferTimerRef.current) {
      clearTimeout(aiBufferTimerRef.current);
      aiBufferTimerRef.current = null;
    }
    setIsAiBuffering(false);
  };

  const abortActiveAiTurn = () => {
    activeAiTurnIdRef.current += 1;
    activeAiTurnAbortRef.current?.abort();
    activeAiTurnAbortRef.current = null;
    streamingRef.current = "";
    setStreamingText("");
    clearAiCaption();
    setIsAiSpeaking(false);
  };

  const clearPreparedAiTurn = () => {
    preparedAiTurnRef.current = null;
    prefetchAbortRef.current?.abort();
    prefetchAbortRef.current = null;
    speculativeUserPrefetchKeyRef.current = null;
  };

  const getBestVoiceTranscript = () => {
    const finalText = finalTranscriptRef.current.trim();
    const interimText = interimTranscriptRef.current.trim();
    if (!finalText) return interimText;
    if (!interimText) return finalText;
    return interimText.length > finalText.length ? interimText : finalText;
  };

  const captureCurrentVoiceTurn = (): OralMessage | null => {
    const text = getBestVoiceTranscript();
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    isListeningRef.current = false;
    setIsListening(false);
    interimTranscriptRef.current = "";
    setInterimTranscript("");
    if (!text) return null;

    const durationMs = Math.max(600, Date.now() - (voiceStartedAtRef.current || Date.now()));
    return {
      speaker: "candidate_d",
      content: text,
      voice: {
        duration_ms: durationMs,
        word_count: text.split(/\s+/).filter(Boolean).length,
        interrupted_ai: interruptedAiRef.current,
        asr_confidence: null,
        transcript_source: "web_speech",
      },
    };
  };

  function handleTimedSectionEnd() {
    const capturedTurn = isListeningRef.current ? captureCurrentVoiceTurn() : null;
    if (phaseRef.current === "discussion") {
      const updatedMessages = capturedTurn
        ? [...messagesRef.current, capturedTurn]
        : messagesRef.current;
      if (capturedTurn) {
        messagesRef.current = updatedMessages;
        setMessages(updatedMessages);
        setUserRounds((r) => r + 1);
      }
      enterPartB(updatedMessages);
      return;
    }

    if (phaseRef.current === "individual_response") {
      const updatedMessages = capturedTurn
        ? [...messagesRef.current, capturedTurn]
        : messagesRef.current;
      if (capturedTurn) {
        messagesRef.current = updatedMessages;
        setMessages(updatedMessages);
        setUserRounds((r) => r + 1);
      }
      void generateFeedback(updatedMessages);
    }
  }

  const buildAiTurnPlanForState = (
    speaker: AiSpeaker,
    currentAgendaIndex: number,
    queueLength: number,
    openedByUserIndex: number | null,
  ): AiTurnPlan => {
    const currentTopic = topicRef.current;
    const agendaItems = currentTopic?.guiding_questions?.filter(Boolean) ?? [];
    const agendaItem = agendaItems[currentAgendaIndex] ?? "anything else you think is important";
    const isFirstAiForAgenda = queueLength === AI_SPEAKERS.length;
    const isLastAiForAgenda = queueLength === 1;
    const agendaIntent: AgendaIntent = currentAgendaIndex >= agendaItems.length
      ? "free_extension"
      : openedByUserIndex === currentAgendaIndex
        ? "respond_to_user_opened_agenda"
        : isFirstAiForAgenda
        ? "open_agenda_item"
        : isLastAiForAgenda
          ? "close_agenda_item"
          : "respond_and_add";
    return {
      speaker,
      agendaIndex: currentAgendaIndex,
      agendaItem,
      previousAgendaItem: currentAgendaIndex > 0
        ? agendaItems[Math.min(currentAgendaIndex - 1, Math.max(agendaItems.length - 1, 0))]
        : undefined,
      agendaIntent,
      agendaStance: chooseAgendaStance(speaker, agendaIntent),
    };
  };

  const buildAiTurnPlan = (
    speaker: AiSpeaker,
    currentAgendaIndex: number,
  ): AiTurnPlan => buildAiTurnPlanForState(
    speaker,
    currentAgendaIndex,
    aiQueueRef.current.length,
    agendaOpenedByUserRef.current,
  );

  const preparedMatchesPlan = (prepared: PreparedAiTurn | null, plan: AiTurnPlan) => {
    return Boolean(prepared)
      && prepared?.speaker === plan.speaker
      && prepared?.agendaIndex === plan.agendaIndex
      && prepared?.agendaItem === plan.agendaItem
      && prepared?.agendaIntent === plan.agendaIntent;
  };

  const clearPartATimer = () => {
    if (partATimerRef.current) {
      clearInterval(partATimerRef.current);
      partATimerRef.current = null;
    }
  };

  const clearPartBTimer = () => {
    if (partBTimerRef.current) {
      clearInterval(partBTimerRef.current);
      partBTimerRef.current = null;
    }
  };

  const startPartATimer = () => {
    clearPartATimer();
    setPartATimeLeft(PART_A_DURATION_SECONDS);
    partATimerRef.current = setInterval(() => {
      setPartATimeLeft((prev) => {
        if (prev <= 1) {
          clearPartATimer();
          handleTimedSectionEnd();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const startPartBTimer = () => {
    clearPartBTimer();
    setPartBTimeLeft(PART_B_DURATION_SECONDS);
    partBTimerRef.current = setInterval(() => {
      setPartBTimeLeft((prev) => {
        if (prev <= 1) {
          clearPartBTimer();
          handleTimedSectionEnd();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const speakAiMessage = (msg: OralMessage): Promise<void> => {
    if (modeRef.current !== "voice" || typeof window === "undefined" || !("speechSynthesis" in window)) {
      return Promise.resolve();
    }
    if (msg.speaker === "candidate_d") return Promise.resolve();

    return new Promise((resolve) => {
      const utterance = new SpeechSynthesisUtterance(msg.content);
      const voiceConfig: Record<string, { pitch: number; rate: number }> = {
        candidate_a: { pitch: 1.05, rate: 1.02 },
        candidate_b: { pitch: 0.9, rate: 0.98 },
        candidate_c: { pitch: 1.15, rate: 1 },
        examiner: { pitch: 0.95, rate: 0.92 },
      };
      const config = voiceConfig[msg.speaker] ?? { pitch: 1, rate: 1 };
      utterance.lang = "en-HK";
      utterance.pitch = config.pitch;
      utterance.rate = config.rate;
      utterance.onend = () => {
        if (ttsResolveRef.current === resolve) ttsResolveRef.current = null;
        resolve();
      };
      utterance.onerror = () => {
        if (ttsResolveRef.current === resolve) ttsResolveRef.current = null;
        resolve();
      };
      ttsResolveRef.current = resolve;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    });
  };

  const revealAiMessageText = (
    previousMessages: OralMessage[],
    msg: OralMessage,
  ): Promise<void> => {
    clearAiCaption();
    const runId = aiCaptionRunIdRef.current;
    const pieces = msg.content.match(/\S+\s*/g) ?? [msg.content];
    let visibleCount = 0;

    return new Promise((resolve) => {
      const publish = (content: string) => {
        const displayMessages = [...previousMessages, { ...msg, content }];
        messagesRef.current = displayMessages;
        setMessages(displayMessages);
      };

      publish("");
      aiCaptionTimerRef.current = setInterval(() => {
        if (runId !== aiCaptionRunIdRef.current) {
          resolve();
          return;
        }
        visibleCount = Math.min(visibleCount + 1, pieces.length);
        publish(pieces.slice(0, visibleCount).join(""));
        if (visibleCount >= pieces.length) {
          if (aiCaptionTimerRef.current) {
            clearInterval(aiCaptionTimerRef.current);
            aiCaptionTimerRef.current = null;
          }
          messagesRef.current = [...previousMessages, msg];
          setMessages(messagesRef.current);
          resolve();
        }
      }, AI_CAPTION_WORD_INTERVAL_MS);
    });
  };

  const enterPartB = (currentMessages: OralMessage[]) => {
    if (partBStartedRef.current) return;
    partBStartedRef.current = true;
    phaseRef.current = "individual_response";
    setPhase("individual_response");
    clearPartATimer();
    clearAiBuffer();
    abortActiveAiTurn();
    clearPreparedAiTurn();
    cancelAiSpeech();
    recognitionRef.current?.abort();
    isListeningRef.current = false;
    setIsListening(false);
    setInterimTranscript("");
    interruptRequestedRef.current = false;
    const question = partBQuestionRef.current || choosePartBQuestion(topicRef.current);
    partBQuestionRef.current = question;
    const examinerMsg: OralMessage = {
      speaker: "examiner",
      content: `That is the end of the group discussion. Now we will move on to the individual response section. ${question}`,
    };
    const updatedMessages = [...currentMessages, examinerMsg];
    messagesRef.current = updatedMessages;
    setMessages(updatedMessages);
    setStreamingText("");
    setPendingAiSpeaker(null);
    pendingAiSpeakerRef.current = null;
    setIsAiSpeaking(false);
    setPartBTimeLeft(PART_B_DURATION_SECONDS);
    void speakAiMessage(examinerMsg).then(startPartBTimer);
  };

  const scheduleNextAiTurn = (currentMessages: OralMessage[]) => {
    if (feedbackInFlightRef.current || phaseRef.current !== "discussion") return;
    let nextAgendaIndex = agendaIndexRef.current;
    if (aiQueueRef.current.length === 0) {
      aiQueueRef.current = shuffledAiQueue(previousAgendaLastAiRef.current);
      setAgendaIndex(nextAgendaIndex);
    }

    const nextSpeaker = aiQueueRef.current[0];
    pendingAiSpeakerRef.current = nextSpeaker;
    setPendingAiSpeaker(nextSpeaker);
    setIsAiBuffering(true);
    setIsAiSpeaking(false);

    aiBufferTimerRef.current = setTimeout(() => {
      aiBufferTimerRef.current = null;
      setIsAiBuffering(false);
      void sendAiTurn(nextSpeaker, currentMessages, nextAgendaIndex);
    }, currentMessages.length === 0 && nextAgendaIndex === 0
      ? FIRST_AI_TURN_BUFFER_MS
      : recentlyClosedAgendaIndexRef.current !== null && nextAgendaIndex > recentlyClosedAgendaIndexRef.current
        ? AGENDA_TRANSITION_BUFFER_MS
        : AI_TURN_BUFFER_MS);
  };

  const generateAiTurnText = async (
    plan: AiTurnPlan,
    currentMessages: OralMessage[],
    signal: AbortSignal,
  ): Promise<string> => {
    let finalContent = "";
    await takeOralTurn(
      {
        topic_id: topicIdRef.current,
        history: currentMessages,
        phase: phaseRef.current,
        mode: modeRef.current,
        speaker: plan.speaker,
        agenda_index: plan.agendaIndex,
        agenda_item: plan.agendaItem,
        previous_agenda_item: plan.previousAgendaItem,
        agenda_intent: plan.agendaIntent,
        agenda_stance: plan.agendaStance,
      },
      {
        onChunk: () => {},
        onTurnEnd: (event) => {
          finalContent = event.content;
        },
        onError: () => {},
      },
      { signal },
    );
    return finalContent;
  };

  const prefetchNextAiTurn = (currentMessages: OralMessage[], basisText?: string) => {
    if (!topicIdRef.current || phaseRef.current !== "discussion" || aiQueueRef.current.length === 0) return;
    const speaker = aiQueueRef.current[0];
    const plan = buildAiTurnPlan(speaker, agendaIndexRef.current);
    if (preparedMatchesPlan(preparedAiTurnRef.current, plan)) return;
    prefetchAbortRef.current?.abort();
    const controller = new AbortController();
    prefetchAbortRef.current = controller;
    void (async () => {
      const content = await generateAiTurnText(plan, currentMessages, controller.signal);
      if (controller.signal.aborted || !content.trim()) return;
      if (phaseRef.current !== "discussion") return;
      preparedAiTurnRef.current = { ...plan, content, basisText };
      if (prefetchAbortRef.current === controller) {
        prefetchAbortRef.current = null;
      }
    })();
  };

  const prefetchNextAgendaOpeningTurn = (currentMessages: OralMessage[]) => {
    if (!topicIdRef.current || phaseRef.current !== "discussion") return;
    const agendaItems = topicRef.current?.guiding_questions?.filter(Boolean) ?? [];
    if (agendaIndexRef.current > agendaItems.length) return;
    aiQueueRef.current = shuffledAiQueue(previousAgendaLastAiRef.current);
    setAgendaIndex(agendaIndexRef.current);
    prefetchNextAiTurn(currentMessages);
  };

  const prefetchFromPartialUserTranscript = (partialText: string) => {
    if (phaseRef.current !== "discussion" || feedbackInFlightRef.current) return;
    const trimmed = partialText.trim();
    const wordCount = trimmed.split(/\s+/).filter(Boolean).length;
    if (wordCount < SPECULATIVE_USER_PREFETCH_MIN_WORDS) return;

    const agendaItems = topicRef.current?.guiding_questions?.filter(Boolean) ?? [];
    const hasAiSpoken = messagesRef.current.some((msg) => AI_SPEAKERS.includes(msg.speaker as AiSpeaker));
    const signal = detectUserAgendaSignal(trimmed, agendaItems, agendaIndexRef.current, hasAiSpoken);
    const speculativeAgendaIndex = signal?.agendaIndex ?? agendaIndexRef.current;
    const speculativeOpenedByUser = signal?.openedByUser ? speculativeAgendaIndex : agendaOpenedByUserRef.current;
    const speculativeQueue = signal
      ? shuffledAiQueue(previousAgendaLastAiRef.current)
      : aiQueueRef.current.length > 0
        ? aiQueueRef.current
        : shuffledAiQueue(previousAgendaLastAiRef.current);
    const speaker = speculativeQueue[0];
    if (!speaker) return;

    const plan = buildAiTurnPlanForState(
      speaker,
      speculativeAgendaIndex,
      speculativeQueue.length,
      speculativeOpenedByUser,
    );
    const key = `${speaker}:${plan.agendaIndex}:${plan.agendaIntent}`;
    if (speculativeUserPrefetchKeyRef.current === key) return;
    speculativeUserPrefetchKeyRef.current = key;
    if (preparedMatchesPlan(preparedAiTurnRef.current, plan)) return;

    prefetchAbortRef.current?.abort();
    const controller = new AbortController();
    prefetchAbortRef.current = controller;
    const speculativeMessages: OralMessage[] = [
      ...messagesRef.current,
      { speaker: "candidate_d", content: trimmed },
    ];
    void (async () => {
      const content = await generateAiTurnText(plan, speculativeMessages, controller.signal);
      if (controller.signal.aborted || !content.trim()) return;
      if (phaseRef.current !== "discussion") return;
      preparedAiTurnRef.current = { ...plan, content, basisText: trimmed };
      if (prefetchAbortRef.current === controller) {
        prefetchAbortRef.current = null;
      }
    })();
  };

  const applyUserAgendaSignal = (content: string) => {
    const agendaItems = topicRef.current?.guiding_questions?.filter(Boolean) ?? [];
    const hasAiSpoken = messagesRef.current.some((msg) => AI_SPEAKERS.includes(msg.speaker as AiSpeaker));
    const recentlyClosedIndex = recentlyClosedAgendaIndexRef.current;
    const bestMatch = findBestAgendaMatch(content, agendaItems);
    const bufferedReplyToClosedAgenda = recentlyClosedIndex !== null
      && bestMatch.bestIndex === recentlyClosedIndex
      && bestMatch.bestScore >= 2;
    const signal = bufferedReplyToClosedAgenda
      ? { agendaIndex: recentlyClosedIndex, openedByUser: true }
      : detectUserAgendaSignal(content, agendaItems, agendaIndexRef.current, hasAiSpoken)
      ?? (!hasAiSpoken && messagesRef.current.length === 0
        ? { agendaIndex: agendaIndexRef.current, openedByUser: true }
        : null);
    if (!signal) return;

    const prepared = preparedAiTurnRef.current;
    const canKeepPrepared = Boolean(prepared)
      && prepared?.agendaIndex === signal.agendaIndex
      && (!signal.openedByUser || prepared?.agendaIntent === "respond_to_user_opened_agenda")
      && (!prepared?.basisText || transcriptLooksCompatible(prepared.basisText, content));

    if (!canKeepPrepared && (signal.agendaIndex !== agendaIndexRef.current || agendaOpenedByUserRef.current !== signal.agendaIndex)) {
      clearPreparedAiTurn();
    }
    agendaIndexRef.current = signal.agendaIndex;
    setAgendaIndex(signal.agendaIndex);
    aiQueueRef.current = canKeepPrepared && prepared
      ? queueStartingWith(prepared.speaker, previousAgendaLastAiRef.current)
      : shuffledAiQueue(previousAgendaLastAiRef.current);
    agendaOpenedByUserRef.current = signal.openedByUser ? signal.agendaIndex : null;
    forceAdvanceAfterBufferedReplyRef.current = bufferedReplyToClosedAgenda ? signal.agendaIndex : null;
    pendingAiSpeakerRef.current = null;
    setPendingAiSpeaker(null);
  };

  const commitAiTurn = (
    speaker: AiSpeaker,
    currentAgendaIndex: number,
    content: string,
  ) => {
    const previousMessages = [...messagesRef.current];
    const newMsg: OralMessage = { speaker, content };
    const updatedMessages = [...previousMessages, newMsg];
    setStreamingText("");

    if (aiQueueRef.current[0] === speaker) {
      aiQueueRef.current = aiQueueRef.current.slice(1);
    } else {
      aiQueueRef.current = aiQueueRef.current.filter((s) => s !== speaker);
    }
    const shouldForceAdvance = forceAdvanceAfterBufferedReplyRef.current === currentAgendaIndex;
    if (shouldForceAdvance) {
      previousAgendaLastAiRef.current = speaker;
      aiQueueRef.current = [];
      agendaIndexRef.current = currentAgendaIndex + 1;
      setAgendaIndex(agendaIndexRef.current);
      forceAdvanceAfterBufferedReplyRef.current = null;
      recentlyClosedAgendaIndexRef.current = null;
    } else if (aiQueueRef.current.length === 0) {
      previousAgendaLastAiRef.current = speaker;
      recentlyClosedAgendaIndexRef.current = currentAgendaIndex;
      agendaIndexRef.current = currentAgendaIndex + 1;
      setAgendaIndex(agendaIndexRef.current);
    }
    if (agendaOpenedByUserRef.current === currentAgendaIndex) {
      agendaOpenedByUserRef.current = null;
    }
    pendingAiSpeakerRef.current = null;
    setPendingAiSpeaker(null);

    void (async () => {
      if (interruptRequestedRef.current) {
        setIsAiSpeaking(false);
        return;
      }
      if (aiQueueRef.current.length === 0) {
        prefetchNextAgendaOpeningTurn(updatedMessages);
      } else {
        prefetchNextAiTurn(updatedMessages);
      }
      await Promise.all([
        revealAiMessageText(previousMessages, newMsg),
        speakAiMessage(newMsg),
      ]);
      if (interruptRequestedRef.current) {
        setIsAiSpeaking(false);
        return;
      }
      setIsAiSpeaking(false);
      scheduleNextAiTurn(updatedMessages);
    })();
  };

  const sendAiTurn = async (
    speaker: AiSpeaker,
    currentMessages: OralMessage[],
    currentAgendaIndex: number,
  ) => {
    if (!topicIdRef.current || feedbackInFlightRef.current) return;
    if (
      recentlyClosedAgendaIndexRef.current !== null
      && currentAgendaIndex > recentlyClosedAgendaIndexRef.current
    ) {
      recentlyClosedAgendaIndexRef.current = null;
    }
    const plan = buildAiTurnPlan(speaker, currentAgendaIndex);
    if (preparedMatchesPlan(preparedAiTurnRef.current, plan)) {
      const prepared = preparedAiTurnRef.current;
      if (!prepared) return;
      preparedAiTurnRef.current = null;
      setIsAiSpeaking(true);
      commitAiTurn(speaker, currentAgendaIndex, prepared.content);
      return;
    }

    setIsAiSpeaking(true);
    streamingRef.current = "";
    const controller = new AbortController();
    prefetchAbortRef.current?.abort();
    prefetchAbortRef.current = null;
    activeAiTurnAbortRef.current?.abort();
    activeAiTurnAbortRef.current = controller;
    const turnId = activeAiTurnIdRef.current + 1;
    activeAiTurnIdRef.current = turnId;

    await takeOralTurn(
      {
        topic_id: topicIdRef.current,
        history: currentMessages,
        phase: phaseRef.current,
        mode: modeRef.current,
        speaker,
        agenda_index: plan.agendaIndex,
        agenda_item: plan.agendaItem,
        previous_agenda_item: plan.previousAgendaItem,
        agenda_intent: plan.agendaIntent,
        agenda_stance: plan.agendaStance,
      },
      {
        onChunk: (text: string) => {
          if (controller.signal.aborted || turnId !== activeAiTurnIdRef.current || phaseRef.current !== "discussion") return;
          streamingRef.current += text;
        },
        onTurnEnd: (event) => {
          if (controller.signal.aborted || turnId !== activeAiTurnIdRef.current || phaseRef.current !== "discussion") return;
          if (activeAiTurnAbortRef.current === controller) {
            activeAiTurnAbortRef.current = null;
          }
          commitAiTurn(speaker, currentAgendaIndex, event.content);
        },
        onError: (msg) => {
          if (controller.signal.aborted || turnId !== activeAiTurnIdRef.current) return;
          if (activeAiTurnAbortRef.current === controller) {
            activeAiTurnAbortRef.current = null;
          }
          setError(msg);
          setIsAiSpeaking(false);
          setStage("error");
        },
      },
      { signal: controller.signal },
    );
    if (activeAiTurnAbortRef.current === controller) {
      activeAiTurnAbortRef.current = null;
    }
  };

  const handleStartPractice = async () => {
    if (!category) return;
    setTopicLoading(true);
    try {
      const selected = await getRandomOralTopic(category);
      setTopic(selected);
      topicRef.current = selected;
      topicIdRef.current = selected.topic_id;
      messagesRef.current = [];
      agendaIndexRef.current = 0;
      setAgendaIndex(0);
      previousAgendaLastAiRef.current = null;
      pendingAiSpeakerRef.current = null;
      setPendingAiSpeaker(null);
      partBQuestionRef.current = "";
      partBStartedRef.current = false;
      recentlyClosedAgendaIndexRef.current = null;
      forceAdvanceAfterBufferedReplyRef.current = null;
      setPartBTimeLeft(PART_B_DURATION_SECONDS);
      aiQueueRef.current = shuffledAiQueue(null);
      agendaOpenedByUserRef.current = null;
      clearPreparedAiTurn();
      prefetchNextAiTurn([]);
      setStage("reading");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to select topic");
      setStage("error");
    } finally {
      setTopicLoading(false);
    }
  };

  const beginDiscussion = () => {
    cancelAiSpeech();
    clearPartBTimer();
    messagesRef.current = [];
    setMessages([]);
    setStreamingText("");
    setUserRounds(0);
    setPhase("discussion");
    phaseRef.current = "discussion";
    setResult(null);
    setError("");
    setIsScoring(false);
    isListeningRef.current = false;
    setIsListening(false);
    setInterimTranscript("");
    feedbackInFlightRef.current = false;
    interruptRequestedRef.current = false;
    agendaIndexRef.current = 0;
    setAgendaIndex(0);
    setPartATimeLeft(PART_A_DURATION_SECONDS);
    setPartBTimeLeft(PART_B_DURATION_SECONDS);
    previousAgendaLastAiRef.current = null;
    agendaOpenedByUserRef.current = null;
    recentlyClosedAgendaIndexRef.current = null;
    forceAdvanceAfterBufferedReplyRef.current = null;
    partBStartedRef.current = false;
    pendingAiSpeakerRef.current = null;
    setPendingAiSpeaker(null);
    partBQuestionRef.current = "";
    if (aiQueueRef.current.length === 0) {
      aiQueueRef.current = shuffledAiQueue(null);
    }
    setStage("discussion");
    startPartATimer();
    scheduleNextAiTurn([]);
  };

  const skipPartA = () => {
    enterPartB(messagesRef.current);
  };

  const submitUserTurn = async (userMsg: OralMessage) => {
    clearAiBuffer();
    interruptRequestedRef.current = false;
    if (phaseRef.current === "discussion") {
      applyUserAgendaSignal(userMsg.content);
    }
    const prepared = preparedAiTurnRef.current;
    if (prepared?.basisText && !transcriptLooksCompatible(prepared.basisText, userMsg.content)) {
      clearPreparedAiTurn();
    }
    const newMessages = [...messagesRef.current, userMsg];
    messagesRef.current = newMessages;
    setMessages(newMessages);
    setUserRounds((r) => r + 1);
    if (phaseRef.current === "individual_response") {
      clearPartBTimer();
      await generateFeedback(newMessages);
      return;
    }
    scheduleNextAiTurn(newMessages);
  };

  const handleVoiceSubmit = async (text: string, startedAt: number, interruptedAi: boolean) => {
    const trimmed = text.trim();
    if (feedbackInFlightRef.current) return;
    if (!trimmed) {
      interruptRequestedRef.current = false;
      setIsListening(false);
      setInterimTranscript("");
      if (phaseRef.current === "discussion") {
        scheduleNextAiTurn(messagesRef.current);
      }
      return;
    }
    const durationMs = Math.max(600, Date.now() - startedAt);
    const voice: OralVoiceMetadata = {
      duration_ms: durationMs,
      word_count: trimmed.split(/\s+/).filter(Boolean).length,
      interrupted_ai: interruptedAi,
      asr_confidence: null,
      transcript_source: "web_speech",
    };
    await submitUserTurn({ speaker: "candidate_d", content: trimmed, voice });
  };

  const startVoiceCapture = () => {
    if (!speechSupported || isScoring) return;
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return;

    interruptedAiRef.current = isAiSpeaking || isAiBuffering;
    interruptRequestedRef.current = isAiSpeaking || isAiBuffering;
    speculativeUserPrefetchKeyRef.current = null;
    prefetchAbortRef.current?.abort();
    prefetchAbortRef.current = null;
    if (isAiBuffering) {
      clearAiBuffer();
    }
    if (isAiSpeaking) {
      abortActiveAiTurn();
    }
    cancelAiSpeech();
    finalTranscriptRef.current = "";
    finalTranscriptSegmentsRef.current = [];
    interimTranscriptRef.current = "";
    voiceStartedAtRef.current = Date.now();
    setInterimTranscript("");
    isListeningRef.current = true;
    setIsListening(true);

    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-HK";
    recognition.onresult = (event) => {
      const finalSegments: string[] = [];
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const resultItem = event.results[i];
        const transcript = (resultItem[0]?.transcript ?? "").trim();
        if (!transcript) continue;
        if (resultItem.isFinal) finalSegments.push(transcript);
        else interimText = [interimText, transcript].filter(Boolean).join(" ");
      }
      if (finalSegments.length > 0) {
        for (const segment of finalSegments) {
          if (finalTranscriptSegmentsRef.current.at(-1) !== segment) {
            finalTranscriptSegmentsRef.current.push(segment);
          }
        }
        finalTranscriptRef.current = finalTranscriptSegmentsRef.current.join(" ").trim();
      }
      const combined = [finalTranscriptRef.current, interimText].filter(Boolean).join(" ");
      interimTranscriptRef.current = combined;
      setInterimTranscript(combined);
      prefetchFromPartialUserTranscript(combined);
    };
    recognition.onerror = () => {
      isListeningRef.current = false;
      setIsListening(false);
    };
    recognition.onend = () => {
      isListeningRef.current = false;
      setIsListening(false);
    };
    recognitionRef.current = recognition;
    recognition.start();
  };

  const stopVoiceCapture = () => {
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    recognition?.stop();
    isListeningRef.current = false;
    setIsListening(false);
    const startedAt = voiceStartedAtRef.current || Date.now();
    const interruptedAi = interruptedAiRef.current;
    window.setTimeout(() => {
      const text = getBestVoiceTranscript();
      interimTranscriptRef.current = "";
      setInterimTranscript("");
      void handleVoiceSubmit(text, startedAt, interruptedAi);
    }, SPEECH_STOP_FLUSH_MS);
  };

  const generateFeedback = async (msgs: OralMessage[]) => {
    if (feedbackInFlightRef.current) return;
    feedbackInFlightRef.current = true;
    setIsScoring(true);
    setIsAiSpeaking(true);
    try {
      const data = await getOralFeedback({
        topic_id: topicIdRef.current,
        history: msgs,
        phase: phaseRef.current,
        mode: modeRef.current,
      });
      setResult(data);
      setStage("feedback");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Feedback failed");
      setStage("error");
    } finally {
      setIsScoring(false);
      setIsAiSpeaking(false);
    }
  };

  const handleNewPractice = () => {
    clearPartATimer();
    clearPartBTimer();
    clearAiBuffer();
    abortActiveAiTurn();
    clearPreparedAiTurn();
    cancelAiSpeech();
    recognitionRef.current?.abort();
    setStage("config");
    setCategory(null);
    setTopic(null);
    messagesRef.current = [];
    setMessages([]);
    setResult(null);
    setUserRounds(0);
    topicIdRef.current = "";
    feedbackInFlightRef.current = false;
    phaseRef.current = "discussion";
    setPhase("discussion");
    setStreamingText("");
    setIsAiSpeaking(false);
    setIsAiBuffering(false);
    isListeningRef.current = false;
    setIsListening(false);
    setInterimTranscript("");
    setIsScoring(false);
    interruptRequestedRef.current = false;
    agendaIndexRef.current = 0;
    setAgendaIndex(0);
    setPartATimeLeft(PART_A_DURATION_SECONDS);
    setPartBTimeLeft(PART_B_DURATION_SECONDS);
    aiQueueRef.current = [];
    previousAgendaLastAiRef.current = null;
    agendaOpenedByUserRef.current = null;
    recentlyClosedAgendaIndexRef.current = null;
    forceAdvanceAfterBufferedReplyRef.current = null;
    pendingAiSpeakerRef.current = null;
    setPendingAiSpeaker(null);
    partBQuestionRef.current = "";
    partBStartedRef.current = false;
  };

  const agendaItems = topic?.guiding_questions?.filter(Boolean) ?? [];
  const agendaLabel = phase === "discussion" && agendaItems.length > 0
    ? agendaIndex >= agendaItems.length
      ? "Part A · Free Discussion"
      : `Part A · Point ${agendaIndex + 1}/${agendaItems.length}: ${agendaItems[agendaIndex]}`
    : "";

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]">
          <ArrowLeft size={14} /> Market
        </Link>
        <span>/</span>
        <Link href="/market/hkdse/english" className="transition-colors hover:text-[var(--foreground)]">English Language</Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">Oral Practice</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10">
          <Globe size={20} className="text-sky-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">English Speaking Practice</h1>
          <p className="text-xs text-[var(--muted-foreground)]">HKDSE Speaking · Group Discussion</p>
        </div>
      </div>

      {stage === "config" && (
        <ConfigStage
          topic={category}
          loading={topicLoading}
          speechSupported={speechSupported}
          onSelectTopic={setCategory}
          onStart={handleStartPractice}
        />
      )}

      {stage === "reading" && topic && (
        <ReadingStage topic={topic} onBegin={beginDiscussion} />
      )}

      {stage === "discussion" && (
        <DiscussionStage
          messages={messages}
          streamingText={streamingText}
          isAiSpeaking={isAiSpeaking}
          isScoring={isScoring}
          isAiBuffering={isAiBuffering}
          pendingAiSpeaker={pendingAiSpeaker}
          agendaLabel={agendaLabel}
          partATimeLeft={partATimeLeft}
          partBTimeLeft={partBTimeLeft}
          isListening={isListening}
          interimTranscript={interimTranscript}
          speechSupported={speechSupported}
          phase={phase}
          onSkipPartA={skipPartA}
          onStartVoice={startVoiceCapture}
          onStopVoice={stopVoiceCapture}
        />
      )}

      {stage === "feedback" && result && (
        <FeedbackStage result={result} onNewPractice={handleNewPractice} />
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">Back to settings</button>
        </div>
      )}
    </div>
  );
}
