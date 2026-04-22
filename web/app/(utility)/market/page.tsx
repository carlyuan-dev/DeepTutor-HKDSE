"use client";

import Link from "next/link";
import {
  ArrowRight,
  Calculator,
  ClipboardCheck,
  FileText,
  Globe,
  Languages,
  Layers,
  type LucideIcon,
} from "lucide-react";

// ── Learning Loop ─────────────────────────────────────────────────────────────

interface ToolCard {
  href: string;
  name: string;
  tagline: string;
  description: string;
  icon: LucideIcon;
  color: string;
  step: number;
}

const TOOLS: ToolCard[] = [
  {
    href: "/market/paper-forge",
    name: "PaperForge",
    tagline: "Generate exam papers",
    description:
      "Create customized examination papers from your knowledge base. Configure question types, difficulty, and scope.",
    icon: FileText,
    color: "text-blue-500",
    step: 1,
  },
  {
    href: "/market/exam-grader",
    name: "ExamGrader",
    tagline: "Grade & analyze answers",
    description:
      "Submit your answers for AI-powered grading. Get per-question feedback and a detailed weak-area breakdown.",
    icon: ClipboardCheck,
    color: "text-emerald-500",
    step: 2,
  },
  {
    href: "/market/flash-deck",
    name: "FlashDeck",
    tagline: "Spaced repetition review",
    description:
      "Review your weak areas with SM-2 scheduled flashcards. Reinforce what you know, master what you don't.",
    icon: Layers,
    color: "text-purple-500",
    step: 3,
  },
  // Add more Learning Loop tools here
];

// ── HKDSE Subjects ────────────────────────────────────────────────────────────

interface SubjectCard {
  href: string;
  code: string;
  name: string;
  nameZh: string;
  tagline: string;
  icon: LucideIcon;
  iconColor: string;
  iconBg: string;
  borderColor: string;
}

const SUBJECTS: SubjectCard[] = [
  {
    href: "/market/hkdse/chinese",
    code: "CHIN",
    name: "Chinese Language",
    nameZh: "中國語文",
    tagline: "閱讀 · 寫作 · 文言文",
    icon: Languages,
    iconColor: "text-rose-500",
    iconBg: "bg-rose-500/10",
    borderColor: "hover:border-rose-500/30",
  },
  {
    href: "/market/hkdse/english",
    code: "ENG",
    name: "English Language",
    nameZh: "英國語文",
    tagline: "Reading · Writing · Integrated Skills",
    icon: Globe,
    iconColor: "text-sky-500",
    iconBg: "bg-sky-500/10",
    borderColor: "hover:border-sky-500/30",
  },
  {
    href: "/market/hkdse/maths",
    code: "MATH",
    name: "Mathematics",
    nameZh: "數學（必修部分）",
    tagline: "Paper 1 · Paper 2 · Topic Drill",
    icon: Calculator,
    iconColor: "text-amber-500",
    iconBg: "bg-amber-500/10",
    borderColor: "hover:border-amber-500/30",
  },
  // Add more HKDSE subjects here
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketPage() {
  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-2">
        <h1 className="text-2xl font-semibold text-[var(--foreground)]">Market</h1>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          Learning tools to supercharge your study experience.
        </p>
      </div>

      {/* ── Section: Learning Loop ── */}
      <div className="mb-4 mt-8 flex items-center gap-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">
          Learning Loop
        </p>
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--muted-foreground)]/50">
          <span>PaperForge</span>
          <ArrowRight size={10} />
          <span>ExamGrader</span>
          <ArrowRight size={10} />
          <span>FlashDeck</span>
          <ArrowRight size={10} />
          <span className="italic">repeat</span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {TOOLS.map((tool, index) => (
          <Link
            key={tool.href}
            href={tool.href}
            className="group relative flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 transition-all duration-150 hover:border-[var(--border)]/80 hover:bg-[var(--background)] hover:shadow-sm"
          >
            <span className="absolute right-4 top-4 text-[11px] text-[var(--muted-foreground)]/50">
              {String(tool.step).padStart(2, "0")}
            </span>
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--background)] group-hover:bg-[var(--secondary)]">
              <tool.icon size={20} strokeWidth={1.6} className={tool.color} />
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-sm font-semibold text-[var(--foreground)]">{tool.name}</p>
              <p className="text-xs font-medium text-[var(--muted-foreground)]">{tool.tagline}</p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--muted-foreground)]/80">
                {tool.description}
              </p>
            </div>
            <div className="mt-auto flex items-center gap-1 text-xs text-[var(--muted-foreground)] transition-colors group-hover:text-[var(--foreground)]">
              <span>Open</span>
              <ArrowRight size={12} className="transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
            {index < TOOLS.length - 1 && (
              <span className="pointer-events-none absolute -right-3 top-1/2 z-10 hidden -translate-y-1/2 text-[var(--muted-foreground)]/40 sm:block">
                <ArrowRight size={14} />
              </span>
            )}
          </Link>
        ))}
      </div>

      {/* ── Section: HKDSE Subjects ── */}
      <div className="mb-4 mt-10 flex items-center gap-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">
          HKDSE Subjects
        </p>
        <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--muted-foreground)]/60">
          Hong Kong Diploma of Secondary Education
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {SUBJECTS.map((subj) => (
          <Link
            key={subj.href}
            href={subj.href}
            className={`group flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 transition-all duration-150 hover:bg-[var(--background)] hover:shadow-sm ${subj.borderColor}`}
          >
            {/* Subject code badge */}
            <div className="flex items-center justify-between">
              <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${subj.iconBg} group-hover:opacity-90`}>
                <subj.icon size={20} strokeWidth={1.6} className={subj.iconColor} />
              </div>
              <span className="rounded-md border border-[var(--border)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--muted-foreground)]/60">
                {subj.code}
              </span>
            </div>

            {/* Text */}
            <div className="flex flex-col gap-0.5">
              <p className="text-sm font-semibold text-[var(--foreground)]">{subj.name}</p>
              <p className={`text-xs font-medium ${subj.iconColor}`}>{subj.nameZh}</p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]/70">{subj.tagline}</p>
            </div>

            <div className="mt-auto flex items-center gap-1 text-xs text-[var(--muted-foreground)] transition-colors group-hover:text-[var(--foreground)]">
              <span>View features</span>
              <ArrowRight size={12} className="transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
