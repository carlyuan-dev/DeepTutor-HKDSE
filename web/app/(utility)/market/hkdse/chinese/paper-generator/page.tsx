"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle, FileText, Loader2 } from "lucide-react";
import { generateChinesePaper } from "@/lib/market-api";
import { listKnowledgeBases } from "@/lib/knowledge-api";
import type { ExamPaper, Question, StudentAnswers } from "@/types/market";
import { STORAGE_KEYS } from "@/types/market";

type Stage = "config" | "generating" | "answer" | "submitting";

export default function ChinesePaperGeneratorPage() {
  const router = useRouter();
  const [kbName, setKbName] = useState("");
  const [kbList, setKbList] = useState<string[]>([]);
  const [title, setTitle] = useState("HKDSE 中國語文 卷一");
  const [passageType, setPassageType] = useState("白話文");
  const [selectedTypes, setSelectedTypes] = useState(["mcq", "short_answer"]);
  const [numQuestions, setNumQuestions] = useState(8);
  const [difficulty, setDifficulty] = useState("medium");
  const [stage, setStage] = useState<Stage>("config");
  const [progressMsg, setProgressMsg] = useState("");
  const [paper, setPaper] = useState<ExamPaper | null>(null);
  const [answers, setAnswers] = useState<StudentAnswers>({});
  const [error, setError] = useState("");

  useEffect(() => {
    listKnowledgeBases().then((kbs) => {
      const names = kbs.map((kb: { name: string }) => kb.name);
      setKbList(names);
      if (names.length > 0) setKbName(names[0]);
    });
  }, []);

  const toggleType = (t: string) =>
    setSelectedTypes((prev) => prev.includes(t) ? (prev.length > 1 ? prev.filter((x) => x !== t) : prev) : [...prev, t]);

  const handleGenerate = async () => {
    setError("");
    setStage("generating");
    setProgressMsg("準備中...");
    try {
      const result = await generateChinesePaper(
        { kb_name: kbName || undefined, title, passage_type: passageType,
          question_types: selectedTypes, num_questions: numQuestions, difficulty },
        (msg) => setProgressMsg(msg)
      );
      setPaper(result);
      const initAnswers: StudentAnswers = {};
      result.questions.forEach((q) => (initAnswers[q.id] = ""));
      setAnswers(initAnswers);
      setStage("answer");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed");
      setStage("config");
    }
  };

  const handleSubmit = () => {
    if (!paper) return;
    setStage("submitting");
    localStorage.setItem(STORAGE_KEYS.paper, JSON.stringify(paper));
    localStorage.setItem(STORAGE_KEYS.answers, JSON.stringify(answers));
    router.push("/market/exam-grader");
  };

  const answeredCount = Object.values(answers).filter((a) => a.trim()).length;

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market/hkdse/chinese" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]"><ArrowLeft size={14} /> Chinese Language</Link>
        <span>/</span><span className="text-[var(--foreground)]">Paper Generator</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-rose-500/10"><FileText size={20} className="text-rose-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">中文試卷生成</h1><p className="text-xs text-[var(--muted-foreground)]">HKDSE 卷一 · 閱讀理解</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-xl space-y-5">
          {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">試卷標題</label>
            <input className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-rose-500/50" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          {kbList.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">知識庫</label>
              <select className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" value={kbName} onChange={(e) => setKbName(e.target.value)}>
                <option value="">不使用知識庫</option>
                {kbList.map((kb) => (<option key={kb} value={kb}>{kb}</option>))}
              </select>
            </div>
          )}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">篇章類型</label>
            <div className="flex gap-2">
              {["白話文", "文言文"].map((p) => (
                <button key={p} onClick={() => setPassageType(p)} className={`rounded-lg border px-4 py-2 text-sm transition-colors ${passageType === p ? "border-rose-500/50 bg-rose-500/10 text-rose-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{p}</button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">題型</label>
            <div className="flex flex-wrap gap-2">
              {[{value:"mcq",label:"選擇題"},{value:"short_answer",label:"短答題"}].map((t) => (
                <button key={t.value} onClick={() => toggleType(t.value)} className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${selectedTypes.includes(t.value) ? "border-rose-500/50 bg-rose-500/10 text-rose-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{t.label}</button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">題目數量</label>
              <input type="number" min={3} max={20} className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" value={numQuestions} onChange={(e) => setNumQuestions(Math.max(3, Math.min(20, Number(e.target.value))))} />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">難度</label>
              <div className="flex gap-1.5">
                {[{value:"easy",label:"容易"},{value:"medium",label:"中等"},{value:"hard",label:"困難"}].map((d) => (
                  <button key={d.value} onClick={() => setDifficulty(d.value)} className={`flex-1 rounded-lg border py-2 text-xs transition-colors ${difficulty === d.value ? "border-rose-500/50 bg-rose-500/10 text-rose-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{d.label}</button>
                ))}
              </div>
            </div>
          </div>
          <button onClick={handleGenerate} className="flex w-full items-center justify-center gap-2 rounded-lg bg-rose-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90">生成試卷 <ArrowRight size={15} /></button>
        </div>
      )}

      {stage === "generating" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-rose-500" /><p className="text-sm text-[var(--muted-foreground)]">{progressMsg}</p></div>
      )}

      {stage === "answer" && paper && (
        <div className="max-w-2xl space-y-6">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-5 py-4">
            <h2 className="text-base font-semibold text-[var(--foreground)]">{paper.title}</h2>
            <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">{paper.questions.length} 題</p>
          </div>

          {/* 閱讀篇章 */}
          {paper.passage && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">閱讀篇章</p>
              <div className="text-sm leading-relaxed text-[var(--foreground)] whitespace-pre-line">{paper.passage}</div>
            </div>
          )}

          {paper.questions.map((q: Question, idx: number) => (
            <div key={q.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <div className="mb-3 flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-xs font-medium text-[var(--foreground)]">{idx + 1}</span>
                <div className="flex-1">
                  <p className="text-sm text-[var(--foreground)]">{q.question}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-[10px] text-[var(--muted-foreground)]/60">{q.topic}</span>
                    <span className="text-[var(--muted-foreground)]/40">·</span>
                    <span className="text-[10px] text-[var(--muted-foreground)]/60">{q.points} 分</span>
                  </div>
                </div>
              </div>
              {q.type === "mcq" && q.options ? (
                <div className="ml-9 space-y-1.5">{q.options.map((opt) => (
                  <button key={opt} onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                    className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm ${answers[q.id] === opt ? "border-rose-500/50 bg-rose-500/10 text-rose-400" : "border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--background)]"}`}>
                    {answers[q.id] === opt && <CheckCircle size={14} className="shrink-0" />}<span>{opt}</span></button>
                ))}</div>
              ) : (
                <textarea className="ml-9 w-[calc(100%-2.25rem)] resize-none rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" rows={3} placeholder="你的答案..." value={answers[q.id] ?? ""} onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))} />
              )}
            </div>
          ))}
          <div className="sticky bottom-0 -mx-8 border-t border-[var(--border)] bg-[var(--background)] px-8 py-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-[var(--muted-foreground)]">{answeredCount} / {paper.questions.length} 已作答</p>
              <button onClick={handleSubmit} disabled={answeredCount === 0} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">提交批改 <ArrowRight size={15} /></button>
            </div>
          </div>
        </div>
      )}

      {stage === "submitting" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-emerald-500" /><p className="text-sm text-[var(--muted-foreground)]">正在提交批改...</p></div>
      )}
    </div>
  );
}
