"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, FileText, Loader2, Star } from "lucide-react";
import { gradeChineseEssay } from "@/lib/market-api";
import { apiUrl } from "@/lib/api";
import type { ChineseEssayRequest, ChineseEssayResult, DimensionScore } from "@/types/market";

function ModelAnswerButton({ title, essay, genre, language }: { title: string; essay: string; genre: string; language: string }) {
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState<any>(null);
  if (!essay) return null;

  const fetchModel = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/essay/model-answer"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, essay: essay.slice(0, 2000), genre, language }),
      });
      const data = await res.json();
      if (!data.error) setModel(data);
    } catch {}
    setLoading(false);
  };

  return (
    <div className="space-y-3">
      <button onClick={fetchModel} disabled={loading}
        className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 ${loading ? "bg-amber-400" : "bg-amber-500"}`}>
        {loading ? <Loader2 size={14} className="animate-spin" /> : <Star size={14} />}
        {loading ? "生成中..." : "生成 5** 範文對比"}
      </button>
      {model && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 space-y-3 max-h-80 overflow-y-auto">
          <p className="text-xs font-medium text-amber-400">⭐ 5** Model Essay ({model.model_essay?.length || 0} 字)</p>
          {model.key_features?.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] text-[var(--muted-foreground)]">Key Features:</p>
              {model.key_features.slice(0, 3).map((f: string, i: number) => (
                <p key={i} className="text-[11px] text-[var(--foreground)]">· {f}</p>
              ))}
            </div>
          )}
          {model.learnable_techniques?.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] text-[var(--muted-foreground)]">可學技巧:</p>
              {model.learnable_techniques.slice(0, 3).map((t: string, i: number) => (
                <p key={i} className="text-[11px] text-amber-400">💡 {t}</p>
              ))}
            </div>
          )}
          {model.model_essay && (
            <details>
              <summary className="cursor-pointer text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">展開範文全文</summary>
              <p className="mt-2 text-sm leading-relaxed text-[var(--foreground)] whitespace-pre-wrap">{model.model_essay}</p>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

type Stage = "config" | "grading" | "result" | "error";

const GENRES = [
  { value: "argumentative", label: "議論文" },
  { value: "narrative", label: "記敘文" },
  { value: "descriptive", label: "描寫文" },
];

function scoreColor(s: DimensionScore) {
  const pct = (s.score / s.max_score) * 100;
  return pct >= 80 ? "text-emerald-400" : pct >= 60 ? "text-yellow-400" : "text-red-400";
}

export default function ChineseEssayGraderPage() {
  const [stage, setStage] = useState<Stage>("config");
  const [title, setTitle] = useState("");
  const [essay, setEssay] = useState("");
  const [genre, setGenre] = useState<ChineseEssayRequest["genre"]>("argumentative");
  const [result, setResult] = useState<ChineseEssayResult | null>(null);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!essay.trim()) return;
    setError("");
    setStage("grading");
    try {
      const res = await gradeChineseEssay({ title, essay, genre });
      setResult(res);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Grading failed");
      setStage("error");
    }
  };

  const totalScoreColor = result
    ? result.percentage >= 80
      ? "text-emerald-400"
      : result.percentage >= 60
      ? "text-yellow-400"
      : "text-red-400"
    : "";

  const totalScoreBg = result
    ? result.percentage >= 80
      ? "bg-emerald-500/10 border-emerald-500/30"
      : result.percentage >= 60
      ? "bg-yellow-500/10 border-yellow-500/30"
      : "bg-red-500/10 border-red-500/30"
    : "";

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market/hkdse/chinese" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]">
          <ArrowLeft size={14} />
          Chinese Language
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">Essay Grader</span>
      </div>

      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-rose-500/10">
          <FileText size={20} className="text-rose-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">中文作文批改</h1>
          <p className="text-xs text-[var(--muted-foreground)]">HKDSE 卷二標準 · 內容 / 表達 / 組織 三維評分</p>
        </div>
      </div>

      {/* ── Config ── */}
      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">文體</label>
            <div className="flex gap-2">
              {GENRES.map((g) => (
                <button
                  key={g.value}
                  onClick={() => setGenre(g.value as ChineseEssayRequest["genre"])}
                  className={`rounded-lg border px-4 py-2 text-sm transition-colors ${
                    genre === g.value
                      ? "border-rose-500/50 bg-rose-500/10 text-rose-400"
                      : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">
              作文題目 <span className="text-[var(--muted-foreground)]/50">(可選)</span>
            </label>
            <input
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-rose-500/50 focus:ring-1 focus:ring-rose-500/20"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. 論科技的雙面性"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">學生作文</label>
            <textarea
              className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-3 text-sm text-[var(--foreground)] outline-none focus:border-rose-500/50 focus:ring-1 focus:ring-rose-500/20"
              rows={14}
              value={essay}
              onChange={(e) => setEssay(e.target.value)}
              placeholder="在此貼上學生作文全文..."
            />
            <p className="text-right text-[10px] text-[var(--muted-foreground)]/50">{essay.length} 字</p>
          </div>

          <button
            onClick={handleSubmit}
            disabled={!essay.trim()}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-rose-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            提交批改
          </button>
        </div>
      )}

      {/* ── Grading ── */}
      {stage === "grading" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-rose-500" />
          <p className="text-sm text-[var(--muted-foreground)]">AI 評分中，請稍候...</p>
        </div>
      )}

      {/* ── Error ── */}
      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button
            onClick={() => setStage("config")}
            className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            返回重試
          </button>
        </div>
      )}

      {/* ── Result ── */}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-6">
          {/* Total score */}
          <div className={`rounded-xl border p-6 ${totalScoreBg}`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[var(--muted-foreground)]">總分</p>
                <p className={`mt-1 text-4xl font-bold ${totalScoreColor}`}>
                  {result.total_score}
                  <span className="text-xl font-normal text-[var(--muted-foreground)]">/{result.max_score}</span>
                </p>
                <p className={`mt-0.5 text-sm font-medium ${totalScoreColor}`}>{result.percentage}%</p>
              </div>
              <div className="text-right text-xs text-[var(--muted-foreground)]">
                <p>內容 · 表達 · 組織</p>
                <p className="mt-1">HKDSE 卷二標準</p>
              </div>
            </div>
          </div>

          {/* Dimension scores */}
          <div className="grid grid-cols-3 gap-3">
            {(
              [
                { key: "content", label: "內容", full: 40 },
                { key: "expression", label: "表達", full: 40 },
                { key: "organization", label: "組織", full: 20 },
              ] as const
            ).map((dim) => {
              const d = result[dim.key];
              return (
                <div key={dim.key} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4 text-center">
                  <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]/60">{dim.label}</p>
                  <p className={`mt-2 text-2xl font-bold ${scoreColor(d)}`}>
                    {d.score}<span className="text-sm font-normal text-[var(--muted-foreground)]">/{d.max_score}</span>
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">{d.comment}</p>
                </div>
              );
            })}
          </div>

          {/* Strengths & Improvements */}
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
              <p className="mb-2 text-xs font-medium text-emerald-400">優點</p>
              <ul className="space-y-1.5">
                {result.strengths.map((s, i) => (
                  <li key={i} className="text-xs leading-relaxed text-[var(--foreground)]">{s}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
              <p className="mb-2 text-xs font-medium text-yellow-400">改進建議</p>
              <ul className="space-y-1.5">
                {result.improvements.map((s, i) => (
                  <li key={i} className="text-xs leading-relaxed text-[var(--foreground)]">{s}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Overall comment */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="mb-2 text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide">整體評語</p>
            <p className="text-sm leading-relaxed text-[var(--foreground)]">{result.overall_comment}</p>
          </div>

          {/* Annotated text */}
          {result.annotated_text && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="mb-3 text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide">原文批注</p>
              <div className="text-sm leading-relaxed text-[var(--foreground)] whitespace-pre-wrap">
                {result.annotated_text.split(/(【批注：[^】]+】)/).map((part, i) => {
                  if (part.startsWith("【批注：")) {
                    return (
                      <span key={i} className="rounded bg-rose-500/10 px-1 py-0.5 text-xs text-rose-400">
                        {part}
                      </span>
                    );
                  }
                  return <span key={i}>{part}</span>;
                })}
              </div>
            </div>
          )}

          {/* ── Ensemble Panel (3-Agent Grading) ── */}
          {(result as any).ensemble && (
            <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/5 p-5">
              <p className="mb-3 text-xs font-medium text-indigo-400 uppercase tracking-wide">
                🤖 多 Agent 辯論評分 · {(result as any).ensemble?.agreement_level === "high" ? "✅" : (result as any).ensemble?.agreement_level === "moderate" ? "⚠️" : "🔴"} {(result as any).ensemble?.agreement_level}
              </p>

              {/* Per-dimension agent scores */}
              <div className="space-y-3 mb-4">
                {(["content", "expression", "organization"] as const).map((dim) => {
                  const d = result[dim] as any;
                  const labels = { content: "內容", expression: "表達", organization: "組織" };
                  const agents = ["嚴格", "寬鬆", "平衡"];
                  return (
                    <div key={dim} className="flex items-center gap-3 text-xs">
                      <span className="w-10 text-[var(--muted-foreground)]">{labels[dim]}</span>
                      <div className="flex gap-1.5 flex-1">
                        {(d?.individual_scores || []).map((s: number, i: number) => {
                          const isMedian = s === d?.score;
                          return (
                            <span key={i} className={`flex-1 rounded px-2 py-1 text-center font-mono ${isMedian ? "bg-indigo-500/20 text-indigo-400 font-bold ring-1 ring-indigo-500/30" : "bg-[var(--background)] text-[var(--muted-foreground)]"}`}>
                              {agents[i]} {s}
                            </span>
                          );
                        })}
                      </div>
                      <span className="w-24 text-right text-[var(--muted-foreground)]/70">
                        範圍 {d?.score_range} · 置信度 {d?.confidence}%
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Confidence breakdown */}
              <div className="border-t border-indigo-500/10 pt-3 flex items-center justify-between text-xs">
                <span className="text-[var(--muted-foreground)]">
                  評分者間一致性: <span className="font-medium text-indigo-400">{(result as any).ensemble?.overall_confidence}%</span>
                  {" · "}
                  {(result as any).ensemble?.confidence_breakdown?.interpretation}
                </span>
              </div>
            </div>
          )}

          {/* ── Self-Reflection Panel ── */}
          {(result as any).reflection?.performed && (
            <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-4">
              <p className="mb-2 text-xs font-medium text-teal-400 uppercase tracking-wide">🪞 自我反思迴路</p>
              <p className="text-xs leading-relaxed text-[var(--foreground)]">
                {(result as any).reflection?.note}
              </p>
              {(result as any).reflection?.score_adjusted && (
                <p className="mt-1 text-xs text-amber-400">⚠️ 本次評分經反思後已自動修正</p>
              )}
            </div>
          )}

          {/* ── 5** Model Answer ── */}
          <ModelAnswerButton title={title} essay={essay} genre={genre} language={"zh"} />

          {/* Action bar */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => { setStage("config"); setResult(null); setEssay(""); }}
              className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]"
            >
              批改新作文
            </button>
            <Link
              href="/market/hkdse/chinese"
              className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]"
            >
              返回中文科
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
