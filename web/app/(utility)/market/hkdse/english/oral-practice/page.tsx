"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Globe,
  Lock,
  Send,
  SkipForward,
  type LucideIcon,
} from "lucide-react";
import { getRandomOralTopic, takeOralTurn, getOralFeedback } from "@/lib/market-api";
import type { OralFeedbackResult, OralMessage, OralTopicResponse, OralTopic } from "@/types/market";

type Stage = "config" | "reading" | "discussion" | "feedback" | "error";

const TOPICS: { key: OralTopic; label: string; icon: LucideIcon }[] = [
  { key: "education", label: "Education & Learning", icon: Globe },
  { key: "technology", label: "Technology & Society", icon: Globe },
  { key: "environment", label: "Environment & Conservation", icon: Globe },
  { key: "social_issues", label: "Social Issues", icon: Globe },
];

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

function scoreColor(score: number, max: number) {
  const pct = (score / max) * 100;
  return pct >= 80 ? "text-emerald-400" : pct >= 60 ? "text-yellow-400" : "text-red-400";
}

// ── Config Stage ─────────────────────────────────────────────────────────────

function ConfigStage({
  topic,
  loading,
  onSelectTopic,
  onStart,
}: {
  topic: OralTopic | null;
  loading: boolean;
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

      <button
        onClick={onStart}
        disabled={!topic || loading}
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
  phase,
  userRounds,
  onSend,
}: {
  messages: OralMessage[];
  streamingText: string;
  isAiSpeaking: boolean;
  phase: string;
  userRounds: number;
  onSend: (text: string) => void;
}) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  useEffect(() => {
    if (!isAiSpeaking && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isAiSpeaking]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isAiSpeaking) return;
    onSend(text);
    setInput("");
  };

  return (
    <div className="flex flex-1 flex-col">
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
        <div className="flex items-center gap-3">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
            }}
            disabled={isAiSpeaking}
            placeholder={isAiSpeaking ? "AI is speaking..." : "Type your response..."}
            className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-4 py-2.5 text-sm text-[var(--foreground)] outline-none transition-colors focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/20 disabled:opacity-40"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isAiSpeaking}
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500 text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            <Send size={16} />
          </button>
        </div>
        <div className="mt-2 flex items-center justify-between text-[10px] text-[var(--muted-foreground)]/50">
          <span>
            {phase === "individual_response"
              ? "Individual Response"
              : `Discussion · Round ${userRounds + 1}`}
          </span>
          {isAiSpeaking && (
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500" />
              AI responding...
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
  const pct = result.percentage;
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
    { key: "pronunciation", label: "Pronunciation & Delivery", data: result.pronunciation_delivery, locked: true },
  ];

  return (
    <div className="max-w-2xl space-y-6">
      <div className={`rounded-xl border p-6 ${totalBg}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-[var(--muted-foreground)]">Overall Score</p>
            <p className={`mt-1 text-4xl font-bold ${totalColor}`}>
              {result.total_score}
              <span className="text-xl font-normal text-[var(--muted-foreground)]">/{result.max_score}</span>
            </p>
            <p className={`mt-0.5 text-sm font-medium ${totalColor}`}>{result.percentage}%</p>
          </div>
          <div className="text-right text-xs text-[var(--muted-foreground)]">
            <p>Communication · Language · Ideas · Pronunciation</p>
            <p className="mt-1">HKDSE Paper 4 Speaking</p>
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
                <p className="mt-1 text-[10px] text-[var(--muted-foreground)]/50">Enable with voice input</p>
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
  const [topic, setTopic] = useState<OralTopicResponse | null>(null);
  const [topicLoading, setTopicLoading] = useState(false);
  const [messages, setMessages] = useState<OralMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [userRounds, setUserRounds] = useState(0);
  const [phase, setPhase] = useState<"discussion" | "individual_response">("discussion");
  const [result, setResult] = useState<OralFeedbackResult | null>(null);
  const [error, setError] = useState("");

  const streamingRef = useRef("");
  const messagesRef = useRef<OralMessage[]>([]);
  const topicIdRef = useRef("");
  const phaseRef = useRef<"discussion" | "individual_response">("discussion");

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const handleStartPractice = async () => {
    if (!category) return;
    setTopicLoading(true);
    try {
      const selected = await getRandomOralTopic(category);
      setTopic(selected);
      topicIdRef.current = selected.topic_id;
      setStage("reading");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to select topic");
      setStage("error");
    } finally {
      setTopicLoading(false);
    }
  };

  const beginDiscussion = () => {
    setMessages([]);
    setStreamingText("");
    setUserRounds(0);
    setPhase("discussion");
    phaseRef.current = "discussion";
    setResult(null);
    setError("");
    setStage("discussion");
    sendTurn([]);
  };

  const sendTurn = async (currentMessages: OralMessage[]) => {
    if (!topicIdRef.current) return;
    setIsAiSpeaking(true);
    streamingRef.current = "";

    await takeOralTurn(
      { topic_id: topicIdRef.current, history: currentMessages, phase: phaseRef.current },
      {
        onChunk: (text: string) => {
          streamingRef.current += text;
          setStreamingText(streamingRef.current);
        },
        onTurnEnd: (event) => {
          const newMsg: OralMessage = {
            speaker: event.speaker as OralMessage["speaker"],
            content: event.content,
          };
          const updatedMessages = [...messagesRef.current, newMsg];
          setMessages(updatedMessages);
          setStreamingText("");

          // ── Feedback → call getOralFeedback ──
          if (event.next_speaker === "feedback") {
            setIsAiSpeaking(false);
            generateFeedback(updatedMessages);
            return;
          }

          // ── Update phase synchronously for next auto-triggered turn ──
          if (event.phase === "individual_response") {
            phaseRef.current = "individual_response";
            setPhase("individual_response");
          }

          // ── User's turn ──
          if (event.next_speaker === "candidate_d") {
            setIsAiSpeaking(false);
            return;
          }

          // ── AI or Examiner speaks next (auto-trigger) ──
          setTimeout(() => sendTurn(updatedMessages), 500);
        },
        onError: (msg) => {
          setError(msg);
          setIsAiSpeaking(false);
          setStage("error");
        },
      },
    );
  };

  const handleUserSend = async (text: string) => {
    const userMsg: OralMessage = { speaker: "candidate_d", content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setUserRounds((r) => r + 1);
    await sendTurn(newMessages);
  };

  const generateFeedback = async (msgs: OralMessage[]) => {
    try {
      const data = await getOralFeedback({
        topic_id: topicIdRef.current,
        history: msgs,
        phase,
      });
      setResult(data);
      setStage("feedback");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Feedback failed");
      setStage("error");
    }
  };

  const handleNewPractice = () => {
    setStage("config");
    setCategory(null);
    setTopic(null);
    setMessages([]);
    setResult(null);
    setUserRounds(0);
    topicIdRef.current = "";
  };

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
          <h1 className="text-xl font-semibold text-[var(--foreground)]">Oral Paper 4 Practice</h1>
          <p className="text-xs text-[var(--muted-foreground)]">HKDSE Paper 4 · Group Discussion</p>
        </div>
      </div>

      {stage === "config" && (
        <ConfigStage
          topic={category}
          loading={topicLoading}
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
          phase={phase}
          userRounds={userRounds}
          onSend={handleUserSend}
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
