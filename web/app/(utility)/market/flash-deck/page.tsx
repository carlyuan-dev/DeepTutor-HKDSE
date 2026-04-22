"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, FileText, Layers, Loader2, RotateCcw } from "lucide-react";
import { applyRating, generateCards } from "@/lib/market-api";
import type { Flashcard, SMRating } from "@/types/market";
import { STORAGE_KEYS } from "@/types/market";

type Stage = "loading" | "generating" | "review" | "complete" | "error";

const RATING_BUTTONS: { rating: SMRating; label: string; color: string }[] = [
  { rating: "again", label: "Again", color: "border-red-500/40 text-red-400 hover:bg-red-500/10" },
  { rating: "hard", label: "Hard", color: "border-orange-500/40 text-orange-400 hover:bg-orange-500/10" },
  { rating: "good", label: "Good", color: "border-blue-500/40 text-blue-400 hover:bg-blue-500/10" },
  { rating: "easy", label: "Easy", color: "border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10" },
];

export default function FlashDeckPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("loading");
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [ratings, setRatings] = useState<SMRating[]>([]);
  const [weakTopics, setWeakTopics] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [manualTopics, setManualTopics] = useState("");
  const [kbName, setKbName] = useState("");
  const [kbList, setKbList] = useState<string[]>([]);
  const didInit = useRef(false);

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;

    // Load knowledge bases for manual mode
    import("@/lib/knowledge-api").then(({ listKnowledgeBases }) => {
      listKnowledgeBases().then((kbs: { name: string }[]) => {
        const names = kbs.map((kb) => kb.name);
        setKbList(names);
        if (names.length > 0) setKbName(names[0]);
      });
    });

    // Try to get weak topics from localStorage
    const raw = localStorage.getItem(STORAGE_KEYS.weakTopics);
    if (raw) {
      try {
        const topics: string[] = JSON.parse(raw);
        setWeakTopics(topics);
        setManualTopics(topics.join(", "));
        // Auto-generate if topics present
        generateFromTopics(topics, undefined, 15);
      } catch {
        setStage("loading"); // fall through to manual
      }
    } else {
      setStage("loading");
    }
  }, []);

  const generateFromTopics = async (topics: string[], kb?: string, count = 15) => {
    if (!topics.length) return;
    setStage("generating");
    setFlipped(false);
    setCurrentIdx(0);
    setRatings([]);
    try {
      const generated = await generateCards(topics, kb, count);
      if (!generated.length) throw new Error("No cards generated");
      setCards(generated);
      localStorage.setItem(STORAGE_KEYS.flashcards, JSON.stringify(generated));
      setStage("review");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Card generation failed");
      setStage("error");
    }
  };

  const handleGenerate = () => {
    const topics = manualTopics
      .split(/[,\n]+/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (!topics.length) return;
    generateFromTopics(topics, kbName || undefined, 15);
  };

  const handleRate = (rating: SMRating) => {
    const updatedCards = [...cards];
    updatedCards[currentIdx] = applyRating(updatedCards[currentIdx], rating);
    setCards(updatedCards);
    setRatings((prev) => [...prev, rating]);
    setFlipped(false);

    if (currentIdx + 1 < cards.length) {
      setCurrentIdx((i) => i + 1);
    } else {
      setStage("complete");
    }
  };

  // ── Stats ─────────────────────────────────────────────────────────────────

  const ratingCounts = ratings.reduce(
    (acc, r) => ({ ...acc, [r]: (acc[r] ?? 0) + 1 }),
    {} as Record<SMRating, number>
  );
  const masteredCount = (ratingCounts.good ?? 0) + (ratingCounts.easy ?? 0);
  const masteryPct = ratings.length ? Math.round((masteredCount / ratings.length) * 100) : 0;

  const currentCard = cards[currentIdx];
  const progress = cards.length ? ((currentIdx) / cards.length) * 100 : 0;

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]">
          <ArrowLeft size={14} />
          Market
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">FlashDeck</span>
      </div>

      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10">
          <Layers size={20} className="text-purple-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">FlashDeck</h1>
          <p className="text-xs text-[var(--muted-foreground)]">Spaced repetition review for your weak areas</p>
        </div>
      </div>

      {/* ── Loading / Manual config ── */}
      {stage === "loading" && (
        <div className="max-w-md space-y-5">
          {weakTopics.length > 0 && (
            <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-xs text-yellow-400">
              Weak topics from ExamGrader: {weakTopics.join(", ")}
            </div>
          )}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Topics to Review</label>
            <textarea
              className="w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-purple-500/50"
              rows={3}
              placeholder="Newton's Laws, Thermodynamics, Wave Motion..."
              value={manualTopics}
              onChange={(e) => setManualTopics(e.target.value)}
            />
          </div>
          {kbList.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Knowledge Base <span className="text-[var(--muted-foreground)]/50">(optional)</span></label>
              <select
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none"
                value={kbName}
                onChange={(e) => setKbName(e.target.value)}
              >
                <option value="">None</option>
                {kbList.map((kb) => <option key={kb} value={kb}>{kb}</option>)}
              </select>
            </div>
          )}
          <button
            onClick={handleGenerate}
            disabled={!manualTopics.trim()}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-purple-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            Generate Flashcards
            <ArrowRight size={15} />
          </button>
        </div>
      )}

      {/* ── Generating ── */}
      {stage === "generating" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-purple-500" />
          <p className="text-sm text-[var(--muted-foreground)]">Generating flashcards...</p>
        </div>
      )}

      {/* ── Error ── */}
      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("loading")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            Try again
          </button>
        </div>
      )}

      {/* ── Review ── */}
      {stage === "review" && currentCard && (
        <div className="flex flex-col items-center">
          {/* Progress bar */}
          <div className="mb-6 w-full max-w-lg">
            <div className="mb-1 flex justify-between text-xs text-[var(--muted-foreground)]">
              <span>{currentIdx + 1} / {cards.length}</span>
              <span className="text-purple-400">{currentCard.topic}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
              <div
                className="h-full rounded-full bg-purple-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Card */}
          <div
            className="relative mb-8 w-full max-w-lg cursor-pointer select-none"
            style={{ perspective: "1000px" }}
            onClick={() => setFlipped((f) => !f)}
          >
            <div
              className="relative transition-transform duration-500"
              style={{ transformStyle: "preserve-3d", transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)" }}
            >
              {/* Front */}
              <div
                className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)] p-8 text-center"
                style={{ backfaceVisibility: "hidden" }}
              >
                <p className="mb-2 text-xs text-[var(--muted-foreground)]">QUESTION</p>
                <p className="text-base text-[var(--foreground)]">{currentCard.front}</p>
                <p className="mt-6 text-xs text-[var(--muted-foreground)]/50">tap to reveal answer</p>
              </div>
              {/* Back */}
              <div
                className="absolute inset-0 rounded-2xl border border-purple-500/30 bg-purple-500/5 p-8 text-center"
                style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
              >
                <p className="mb-2 text-xs text-purple-400">ANSWER</p>
                <p className="text-base text-[var(--foreground)]">{currentCard.back}</p>
              </div>
            </div>
          </div>

          {/* Rating buttons — only shown after flip */}
          {flipped && (
            <div className="flex gap-3">
              {RATING_BUTTONS.map(({ rating, label, color }) => (
                <button
                  key={rating}
                  onClick={() => handleRate(rating)}
                  className={`rounded-xl border px-5 py-2.5 text-sm font-medium transition-colors ${color}`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {!flipped && (
            <p className="text-xs text-[var(--muted-foreground)]/50">Rate after revealing</p>
          )}
        </div>
      )}

      {/* ── Complete ── */}
      {stage === "complete" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6">
          <div className="text-center">
            <p className="text-4xl font-bold text-purple-400">{masteryPct}%</p>
            <p className="mt-1 text-sm text-[var(--muted-foreground)]">mastered this session</p>
          </div>

          {/* Rating breakdown */}
          <div className="flex gap-4 text-xs">
            {RATING_BUTTONS.map(({ rating, label, color }) => (
              <div key={rating} className="text-center">
                <p className={`font-medium ${color.split(" ")[1]}`}>{ratingCounts[rating] ?? 0}</p>
                <p className="text-[var(--muted-foreground)]">{label}</p>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex flex-wrap justify-center gap-3">
            <button
              onClick={() => { setStage("review"); setCurrentIdx(0); setRatings([]); setFlipped(false); }}
              className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-4 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]"
            >
              <RotateCcw size={14} />
              Review Again
            </button>
            <button
              onClick={() => router.push("/market/paper-forge")}
              className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90"
            >
              <FileText size={14} />
              Test Yourself Again
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
