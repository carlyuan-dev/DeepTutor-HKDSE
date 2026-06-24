"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Archive,
  ArrowRight,
  BookA,
  BookMarked,
  Brackets,
  Calculator,
  CalendarClock,
  ClipboardCheck,
  Cloud,
  Cpu,
  FileText,
  Globe,
  GraduationCap,
  Languages,
  Layers,
  Lightbulb,
  ListChecks,
  MessagesSquare,
  Network,
  NotebookPen,
  PenLine,
  SpellCheck,
  Stethoscope,
  Timer,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { apiUrl } from "@/lib/api";

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
];

// ── Themed tool sections (the full learning chain) ──────────────────────────────

interface KitCard {
  href: string;
  name: string;
  tagline: string;
  icon: LucideIcon;
  color: string;
  bg: string;
}

interface ToolSection {
  label: string;
  badge: string;
  tools: KitCard[];
}

const SECTIONS: ToolSection[] = [
  {
    label: "Plan & Diagnose",
    badge: "Know where you stand",
    tools: [
      { href: "/market/study-planner", name: "Study Planner", tagline: "Personalized revision schedule", icon: CalendarClock, color: "text-indigo-500", bg: "bg-indigo-500/10" },
      { href: "/market/diagnostic", name: "Diagnostic Quiz", tagline: "Pinpoint weak topics fast", icon: Stethoscope, color: "text-rose-500", bg: "bg-rose-500/10" },
      { href: "/market/concept-map", name: "Concept Map", tagline: "Visualize how ideas connect", icon: Network, color: "text-sky-500", bg: "bg-sky-500/10" },
    ],
  },
  {
    label: "Learn & Understand",
    badge: "Build deep understanding",
    tools: [
      { href: "/market/concept-explainer", name: "Concept Explainer", tagline: "Analogies, examples, pitfalls", icon: Lightbulb, color: "text-yellow-500", bg: "bg-yellow-500/10" },
      { href: "/market/socratic", name: "Socratic Tutor", tagline: "Guided by questions, not answers", icon: MessagesSquare, color: "text-blue-500", bg: "bg-blue-500/10" },
      { href: "/market/step-solver", name: "Step Solver", tagline: "Step-by-step worked solutions", icon: ListChecks, color: "text-cyan-500", bg: "bg-cyan-500/10" },
      { href: "/market/note-maker", name: "Smart Notes", tagline: "Structured notes in seconds", icon: NotebookPen, color: "text-teal-500", bg: "bg-teal-500/10" },
      { href: "/market/translator", name: "Translator & Glossary", tagline: "Translate and learn key terms", icon: Languages, color: "text-emerald-500", bg: "bg-emerald-500/10" },
    ],
  },
  {
    label: "Practice & Drill",
    badge: "Reps build mastery",
    tools: [
      { href: "/market/flash-quiz", name: "Flash Quiz", tagline: "Rapid-fire practice", icon: Zap, color: "text-yellow-500", bg: "bg-yellow-500/10" },
      { href: "/market/cloze", name: "Cloze Practice", tagline: "Fill-in-the-blank recall", icon: Brackets, color: "text-amber-500", bg: "bg-amber-500/10" },
      { href: "/market/past-paper", name: "Past Paper Practice", tagline: "Grounded in real papers", icon: Archive, color: "text-stone-500", bg: "bg-stone-500/10" },
      { href: "/market/mock-exam", name: "Timed Mock Exam", tagline: "Real exam simulation", icon: Timer, color: "text-red-500", bg: "bg-red-500/10" },
      { href: "/market/vocab-builder", name: "Vocabulary Builder", tagline: "Words, examples, mnemonics", icon: BookA, color: "text-lime-500", bg: "bg-lime-500/10" },
    ],
  },
  {
    label: "Write",
    badge: "Express it clearly",
    tools: [
      { href: "/market/essay-outline", name: "Essay Outline", tagline: "Thesis and structure", icon: PenLine, color: "text-fuchsia-500", bg: "bg-fuchsia-500/10" },
      { href: "/market/writing-coach", name: "Writing Coach", tagline: "Polish and learn from fixes", icon: SpellCheck, color: "text-pink-500", bg: "bg-pink-500/10" },
    ],
  },
  {
    label: "Reflect & Master",
    badge: "Close the gaps",
    tools: [
      { href: "/market/mistake-book", name: "Mistake Notebook", tagline: "Learn from every error", icon: BookMarked, color: "text-orange-500", bg: "bg-orange-500/10" },
      { href: "/market/feynman", name: "Feynman Self-Check", tagline: "Explain it to find the gaps", icon: GraduationCap, color: "text-violet-500", bg: "bg-violet-500/10" },
    ],
  },
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
  { href: "/market/hkdse/chinese", code: "CHIN", name: "Chinese Language", nameZh: "中國語文", tagline: "閱讀 · 寫作 · 文言文", icon: Languages, iconColor: "text-rose-500", iconBg: "bg-rose-500/10", borderColor: "hover:border-rose-500/30" },
  { href: "/market/hkdse/english", code: "ENG", name: "English Language", nameZh: "英國語文", tagline: "Reading · Writing · Integrated Skills", icon: Globe, iconColor: "text-sky-500", iconBg: "bg-sky-500/10", borderColor: "hover:border-sky-500/30" },
  { href: "/market/hkdse/maths", code: "MATH", name: "Mathematics", nameZh: "數學（必修部分）", tagline: "Paper 1 · Paper 2 · Topic Drill", icon: Calculator, iconColor: "text-amber-500", iconBg: "bg-amber-500/10", borderColor: "hover:border-amber-500/30" },
];

// ── Engine status badge ─────────────────────────────────────────────────────────

interface LlmStatus { display_name: string; model: string; is_local: boolean; }

function EngineBadge() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<LlmStatus | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl("/api/v1/market-tools/llm-status"))
      .then((r) => r.json())
      .then((d) => { if (!cancelled && !d.error) setStatus(d); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  if (!status) return null;
  const Icon = status.is_local ? Cpu : Cloud;
  return (
    <span title={`${status.display_name} · ${status.model}`}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${status.is_local ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-500" : "border-[var(--border)] bg-[var(--secondary)] text-[var(--muted-foreground)]"}`}>
      <Icon size={12} />
      {status.is_local ? t("Local · Offline") : t("Cloud")}
      <span className="opacity-60">· {status.model}</span>
    </span>
  );
}

// ── Section renderer ────────────────────────────────────────────────────────────

function ToolGrid({ section }: { section: ToolSection }) {
  const { t } = useTranslation();
  return (
    <>
      <div className="mb-4 mt-10 flex items-center gap-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">{t(section.label)}</p>
        <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--muted-foreground)]/60">{t(section.badge)}</span>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {section.tools.map((tool) => (
          <Link key={tool.href} href={tool.href}
            className="group flex flex-col gap-3 rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 transition-all duration-150 hover:bg-[var(--background)] hover:shadow-sm">
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${tool.bg}`}>
              <tool.icon size={20} strokeWidth={1.6} className={tool.color} />
            </div>
            <div className="flex flex-col gap-0.5">
              <p className="text-sm font-semibold text-[var(--foreground)]">{t(tool.name)}</p>
              <p className="text-xs text-[var(--muted-foreground)]/80">{t(tool.tagline)}</p>
            </div>
            <div className="mt-auto flex items-center gap-1 text-xs text-[var(--muted-foreground)] transition-colors group-hover:text-[var(--foreground)]">
              <span>{t("Open")}</span>
              <ArrowRight size={12} className="transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketPage() {
  const { t } = useTranslation();
  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-2 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)]">{t("Market")}</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">{t("A full-circle learning ecosystem — plan, learn, practice, assess, and master.")}</p>
        </div>
        <EngineBadge />
      </div>

      {/* ── Section: Learning Loop ── */}
      <div className="mb-4 mt-8 flex items-center gap-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">{t("Learning Loop")}</p>
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--muted-foreground)]/50">
          <span>PaperForge</span><ArrowRight size={10} /><span>ExamGrader</span><ArrowRight size={10} /><span>FlashDeck</span><ArrowRight size={10} /><span className="italic">{t("repeat")}</span>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {TOOLS.map((tool, index) => (
          <Link key={tool.href} href={tool.href}
            className="group relative flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 transition-all duration-150 hover:border-[var(--border)]/80 hover:bg-[var(--background)] hover:shadow-sm">
            <span className="absolute right-4 top-4 text-[11px] text-[var(--muted-foreground)]/50">{String(tool.step).padStart(2, "0")}</span>
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--background)] group-hover:bg-[var(--secondary)]">
              <tool.icon size={20} strokeWidth={1.6} className={tool.color} />
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-sm font-semibold text-[var(--foreground)]">{tool.name}</p>
              <p className="text-xs font-medium text-[var(--muted-foreground)]">{t(tool.tagline)}</p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--muted-foreground)]/80">{t(tool.description)}</p>
            </div>
            <div className="mt-auto flex items-center gap-1 text-xs text-[var(--muted-foreground)] transition-colors group-hover:text-[var(--foreground)]">
              <span>{t("Open")}</span>
              <ArrowRight size={12} className="transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
            {index < TOOLS.length - 1 && (
              <span className="pointer-events-none absolute -right-3 top-1/2 z-10 hidden -translate-y-1/2 text-[var(--muted-foreground)]/40 sm:block"><ArrowRight size={14} /></span>
            )}
          </Link>
        ))}
      </div>

      {/* ── Themed sections ── */}
      {SECTIONS.map((section) => (<ToolGrid key={section.label} section={section} />))}

      {/* ── Section: HKDSE Subjects ── */}
      <div className="mb-4 mt-10 flex items-center gap-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">{t("HKDSE Subjects")}</p>
        <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--muted-foreground)]/60">{t("Hong Kong Diploma of Secondary Education")}</span>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {SUBJECTS.map((subj) => (
          <Link key={subj.href} href={subj.href}
            className={`group flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 transition-all duration-150 hover:bg-[var(--background)] hover:shadow-sm ${subj.borderColor}`}>
            <div className="flex items-center justify-between">
              <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${subj.iconBg} group-hover:opacity-90`}>
                <subj.icon size={20} strokeWidth={1.6} className={subj.iconColor} />
              </div>
              <span className="rounded-md border border-[var(--border)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--muted-foreground)]/60">{subj.code}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <p className="text-sm font-semibold text-[var(--foreground)]">{t(subj.name)}</p>
              <p className={`text-xs font-medium ${subj.iconColor}`}>{subj.nameZh}</p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]/70">{subj.tagline}</p>
            </div>
            <div className="mt-auto flex items-center gap-1 text-xs text-[var(--muted-foreground)] transition-colors group-hover:text-[var(--foreground)]">
              <span>{t("View features")}</span>
              <ArrowRight size={12} className="transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
