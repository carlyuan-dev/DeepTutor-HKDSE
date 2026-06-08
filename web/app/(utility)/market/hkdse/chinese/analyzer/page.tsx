"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, BookOpen, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "analyzing" | "result" | "error";

interface AnalysisResult {
  title: string;
  author: string;
  sentences: { original: string; translation: string; keywords: { word: string; meaning: string }[] }[];
  comprehension_questions: { id: string; question: string; answer: string; explanation: string }[];
}

export default function ClassicalChineseAnalyzerPage() {
  const [stage, setStage] = useState<Stage>("config");
  const [passage, setPassage] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const [showAnswers, setShowAnswers] = useState<Record<string, boolean>>({});

  const handleSubmit = async () => {
    if (!passage.trim()) return;
    setError("");
    setStage("analyzing");
    try {
      const res = await fetch(apiUrl("/api/v1/hkdse/chinese/analyze-classical"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passage }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed");
      setStage("error");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market/hkdse/chinese" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> Chinese Language</Link>
        <span>/</span><span className="text-[var(--foreground)]">Classical Chinese</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10"><BookOpen size={20} className="text-amber-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">文言文精讀助手</h1><p className="text-xs text-[var(--muted-foreground)]">逐句語譯 · 字詞注釋 · 理解題練習</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">文言文原文</label>
            <textarea className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-3 text-sm text-[var(--foreground)] outline-none focus:border-amber-500/50" rows={10}
              value={passage} onChange={(e) => setPassage(e.target.value)}
              placeholder={"請貼上文言文段落，例如：\n\n學而時習之，不亦說乎？有朋自遠方來，不亦樂乎？人不知而不慍，不亦君子乎？"} />
          </div>
          <button onClick={handleSubmit} disabled={!passage.trim()} className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">開始分析</button>
        </div>
      )}

      {stage === "analyzing" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-amber-500" /><p className="text-sm text-[var(--muted-foreground)]">AI 分析中...</p></div>
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">返回</button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="max-w-2xl space-y-6">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
            <h2 className="text-lg font-semibold text-[var(--foreground)]">{result.title}</h2>
            {result.author && <p className="mt-1 text-sm text-[var(--muted-foreground)]">{result.author}</p>}
          </div>

          <div className="space-y-4">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">逐句語譯</p>
            {result.sentences.map((s, i) => (
              <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
                <p className="text-sm font-medium text-[var(--foreground)]">{s.original}</p>
                <p className="mt-1 text-sm text-[var(--muted-foreground)]">→ {s.translation}</p>
                {s.keywords.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {s.keywords.map((kw, j) => (
                      <span key={j} className="rounded-md bg-amber-500/10 px-2 py-0.5 text-xs">
                        <span className="font-medium text-amber-400">{kw.word}</span>
                        <span className="text-[var(--muted-foreground)]">：{kw.meaning}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {result.comprehension_questions.length > 0 && (
            <div className="space-y-4">
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">理解題練習</p>
              {result.comprehension_questions.map((q) => (
                <div key={q.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
                  <p className="text-sm font-medium text-[var(--foreground)]">{q.question}</p>
                  <button onClick={() => setShowAnswers((prev) => ({ ...prev, [q.id]: !prev[q.id] }))}
                    className="mt-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                    {showAnswers[q.id] ? "隱藏答案" : "顯示答案"}
                  </button>
                  {showAnswers[q.id] && (
                    <div className="mt-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3">
                      <p className="text-sm font-medium text-emerald-400">答案：{q.answer}</p>
                      <p className="mt-1 text-xs text-[var(--muted-foreground)]">{q.explanation}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <button onClick={() => { setStage("config"); setResult(null); setPassage(""); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">分析新篇章</button>
        </div>
      )}
    </div>
  );
}
