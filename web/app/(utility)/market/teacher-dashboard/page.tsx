"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";
import {
  ArrowLeft, BarChart3, BookMarked, CalendarClock, FileText,
  Layers, Loader2, Stethoscope, TrendingUp,
} from "lucide-react";

interface DashboardData {
  overview: {
    total_mistakes: number; active_reviews: number; mastered_topics: number;
    diagnostics_completed: number; knowledge_bases: number;
  };
  topic_heatmap: { topic: string; count: number }[];
  error_type_distribution: Record<string, number>;
  progress: { date: string; subject: string; percentage: number; weak_topics: string[] }[];
  recommended_actions: { action: string; count?: number; link: string; priority: string }[];
}

const PRIORITY_COLORS: Record<string, string> = {
  high: "border-rose-500/30 bg-rose-500/5",
  warning: "border-amber-500/30 bg-amber-500/5",
  normal: "border-[var(--border)] bg-[var(--secondary)]",
};

export default function TeacherDashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(apiUrl("/api/v1/market-tools/dashboard/overview"))
      .then((r) => r.json())
      .then((d) => { if (!d.error) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex h-full items-center justify-center">
      <Loader2 size={36} className="animate-spin text-[var(--muted-foreground)]" />
    </div>
  );

  if (!data) return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-[var(--muted-foreground)]">Unable to load dashboard. Start using the tools to populate data.</p>
    </div>
  );

  const maxTopicCount = Math.max(1, ...data.topic_heatmap.map((t) => t.count));

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> Market</Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">Teacher Dashboard</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
          <BarChart3 size={20} className="text-indigo-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">Teacher Dashboard</h1>
          <p className="text-xs text-[var(--muted-foreground)]">Aggregated overview of student learning data across all tools</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ── Left column: Overview + Progress ── */}
        <div className="lg:col-span-2 space-y-6">
          {/* Overview cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[
              { label: "Total Mistakes", value: data.overview.total_mistakes, icon: BookMarked, color: "text-rose-400" },
              { label: "Due Reviews", value: data.overview.active_reviews, icon: CalendarClock, color: "text-amber-400" },
              { label: "Mastered", value: data.overview.mastered_topics, icon: TrendingUp, color: "text-emerald-400" },
              { label: "Diagnostics", value: data.overview.diagnostics_completed, icon: Stethoscope, color: "text-blue-400" },
              { label: "Knowledge Bases", value: data.overview.knowledge_bases, icon: Layers, color: "text-violet-400" },
            ].map((card) => (
              <div key={card.label} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4 text-center">
                <card.icon size={18} className={`mx-auto mb-1.5 ${card.color}`} />
                <p className="text-2xl font-bold text-[var(--foreground)]">{card.value}</p>
                <p className="text-[10px] text-[var(--muted-foreground)]">{card.label}</p>
              </div>
            ))}
          </div>

          {/* Topic Weakness Heatmap */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
            <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">Topic Weakness Heatmap</p>
            {data.topic_heatmap.length === 0 ? (
              <p className="text-xs text-[var(--muted-foreground)]">No data yet. Use Diagnostic Quiz and Mistake Notebook to populate.</p>
            ) : (
              <div className="space-y-2">
                {data.topic_heatmap.map((t) => (
                  <div key={t.topic} className="flex items-center gap-3">
                    <span className="w-28 shrink-0 truncate text-xs text-[var(--foreground)]">{t.topic}</span>
                    <div className="flex-1 h-4 rounded-full bg-[var(--background)] overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${t.count >= 5 ? "bg-rose-500" : t.count >= 3 ? "bg-amber-500" : "bg-indigo-500"}`}
                        style={{ width: `${Math.max(5, (t.count / maxTopicCount) * 100)}%` }}
                      />
                    </div>
                    <span className="w-8 text-right text-xs font-mono text-[var(--muted-foreground)]">{t.count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Progress Timeline */}
          {data.progress.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">Diagnostic Progress</p>
              <div className="space-y-2">
                {data.progress.map((p, i) => (
                  <div key={i} className="flex items-center gap-3 text-xs">
                    <span className="w-20 text-[var(--muted-foreground)]">{p.date}</span>
                    <span className="w-16 text-[var(--foreground)] font-medium">{p.subject}</span>
                    <div className="flex-1 h-2 rounded-full bg-[var(--background)]">
                      <div
                        className={`h-full rounded-full ${p.percentage >= 80 ? "bg-emerald-500" : p.percentage >= 60 ? "bg-amber-500" : "bg-rose-500"}`}
                        style={{ width: `${p.percentage}%` }}
                      />
                    </div>
                    <span className="w-10 text-right font-mono text-[var(--muted-foreground)]">{p.percentage}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Right column: Actions + Quick Links ── */}
        <div className="space-y-6">
          {/* Recommended Actions */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
            <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">Recommended Actions</p>
            <div className="space-y-2">
              {data.recommended_actions.map((a, i) => (
                <Link key={i} href={a.link}
                  className={`block rounded-lg border p-3 transition-colors hover:bg-[var(--background)] ${PRIORITY_COLORS[a.priority] || ""}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-[var(--foreground)]">{a.action}</span>
                    {a.count !== undefined && (
                      <span className="text-[10px] font-mono text-[var(--muted-foreground)]">{a.count}</span>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Error Type Distribution */}
          {Object.keys(data.error_type_distribution).length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">Error Types</p>
              <div className="space-y-2">
                {Object.entries(data.error_type_distribution).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between text-xs">
                    <span className="text-[var(--foreground)] capitalize">{type.replace("-", " ")}</span>
                    <span className="font-mono text-[var(--muted-foreground)]">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quick Links */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">Quick Tools</p>
            <div className="space-y-1.5">
              {[
                { href: "/market/diagnostic", label: "Diagnostic Quiz", icon: Stethoscope },
                { href: "/market/study-planner", label: "Study Planner", icon: CalendarClock },
                { href: "/market/paper-forge", label: "PaperForge", icon: FileText },
                { href: "/market/mistake-book", label: "Mistake Notebook", icon: BookMarked },
              ].map((q) => (
                <Link key={q.href} href={q.href}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-[var(--foreground)] transition-colors">
                  <q.icon size={14} /> {q.label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
