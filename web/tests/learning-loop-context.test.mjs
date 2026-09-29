/**
 * Offline, fixed-response regression suite. Executes real page callbacks, effects,
 * storage and market-api payloads; only HTTP, routing and React hooks are doubled.
 * AST instrumentation exposes page locals and its JSX element tree. Explicit
 * rerenders/cleanup exercise effect guards, not browser rendering or React's scheduler.
 * Run: node --test web/tests/learning-loop-context.test.mjs
 *
 * Frontend contract:
 * - dtmarket_learning_loop is one submission envelope: id, subject, kb_name
 *   (empty string means no KB), entry, paper (including passage), answers,
 *   weak_topics: []. Every submit, including edited resubmits, gets a fresh id.
 * - dtmarket_learning_loop_result:<id> stores {practice_id, result}; an empty
 *   result.weak_topics replaces earlier weaknesses. Legacy global keys are ignored.
 * - Retake URL is the original entry + ?practice=<id>. The target validates id
 *   and entry, restores subject/KB/focus, then sends topic_focus on its first
 *   generation request. Missing KB blocks requests, never picks another silently.
 * - Grade payload adds optional passage, subject, kb_name. Generic PaperForge
 *   requires an explicit subject; it does not infer all-subject capabilities.
 * - storage + learning-loop-change invalidate current submissions;
 *   learning-loop-result-change invalidates same-window FlashDeck consumers.
 * - Cross-tab guarantee: current-id checks before/after commit and per-id result
 *   keys prevent A from overwriting B. localStorage is NOT an atomic CAS; an
 *   interleaving can leave an unused A result key. This is not account isolation,
 *   backend persistence, cross-day scheduling, or browser/React lifecycle E2E.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const currentKey = "dtmarket_learning_loop";
const routes = {
  chinese: "/market/hkdse/chinese/paper-generator",
  english: "/market/hkdse/english/paper-generator",
  mathematics: "/market/paper-forge",
};
const paper = { title: "Fixed paper", passage: "Original reading passage.", questions: [
  { id: "q1", type: "short_answer", topic: "inference", question: "Why?", answer: "Because", explanation: "Evidence", points: 2 },
] };
const grade = (topics) => ({ results: [{ question_id: "q1", score: 1, max_score: 2, is_correct: false,
  comment: "Explain evidence", correct_answer: "Because" }], total_score: 1, max_score: 2,
  percentage: 50, weak_topics: topics, summary: "Fixed feedback" });
const cards = [{ id: "c1", front: "Why?", back: "Because", topic: "inference", interval: 0, ease_factor: 2.5, repetitions: 0 }];
function storage() {
  const data = new Map();
  return { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: k => data.delete(k) };
}
function seed(store, id, subject = "english", topics = []) {
  const context = { id, subject, kb_name: `${subject}-kb`, entry: routes[subject], weak_topics: topics,
    paper, answers: { q1: "My answer" } };
  store.setItem(currentKey, JSON.stringify(context));
  // Legacy mirrors intentionally disagree: new readers must never trust them.
  store.setItem("dtmarket_paper", JSON.stringify(paper));
  store.setItem("dtmarket_answers", JSON.stringify(context.answers));
  store.setItem("dtmarket_weak_topics", JSON.stringify(["STALE LEGACY TOPIC"]));
  return context;
}
const plain = value => JSON.parse(JSON.stringify(value));
async function flush() { for (let i = 0; i < 20; i++) await Promise.resolve(); }
function elements(node, predicate) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(child => elements(child, predicate));
  return [...(predicate(node) ? [node] : []), ...elements(node.props?.children, predicate)];
}
function textContent(node) {
  if (Array.isArray(node)) return node.map(textContent).join("");
  if (node && typeof node === "object") return textContent(node.props?.children);
  return typeof node === "string" ? node : "";
}
const button = (h, label) => elements(h.api.view, n => n.type === "button" && textContent(n).includes(label))[0];

function mount(route, { store = storage(), search = "", listeners = new Map(), knowledgeBases = ["other-kb", "english-kb", "chinese-kb", "mathematics-kb"] } = {}) {
  const requests = [], pushes = [], cache = new Map();
  const state = {}, setters = {}, slots = [], effects = [];
  let slot = 0, stateIndex = 0, stateNames = [], api, reloads = 0;
  const hooks = {
    useState(initial) {
      const i = slot++, name = stateNames[stateIndex++];
      if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial;
      state[name] = slots[i];
      const set = value => { slots[i] = typeof value === "function" ? value(slots[i]) : value; state[name] = slots[i]; };
      setters[name] = set;
      return [slots[i], set];
    },
    useRef(value) { const i = slot++; return slots[i] ??= { current: value }; },
    useEffect(callback, deps) {
      const i = slot++, old = slots[i];
      if (!old || !deps || deps.some((d, n) => d !== old.deps[n])) {
        effects.push(() => { old?.cleanup?.(); slots[i] = { deps, cleanup: callback() }; });
      }
    },
  };
  const window = { localStorage: store, location: { search, pathname: route, reload: () => reloads++ },
    addEventListener: (type, cb) => { const list = listeners.get(type) ?? new Set(); list.add(cb); listeners.set(type, list); },
    removeEventListener: (type, cb) => listeners.get(type)?.delete(cb),
    dispatchEvent: event => listeners.get(event.type)?.forEach(cb => cb(event)),
  };
  const mocks = {
    react: hooks, "next/navigation": { useRouter: () => ({ push: path => pushes.push(path) }) },
    "next/link": () => null, "lucide-react": {},
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    "@/lib/api": { apiUrl: path => path },
    "@/lib/knowledge-api": { listKnowledgeBases: async () => knowledgeBases.map(name => ({ name })) },
  };
  function load(specifier) {
    if (specifier in mocks) return mocks[specifier];
    if (cache.has(specifier)) return cache.get(specifier);
    const path = specifier.startsWith("@/") ? `../${specifier.slice(2)}.ts` : specifier;
    let source = readFileSync(new URL(path, import.meta.url), "utf8");
    if (path.endsWith("page.tsx")) {
      const tree = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      const page = tree.statements.find(n => ts.isFunctionDeclaration(n) && n.modifiers?.some(m => m.kind === ts.SyntaxKind.DefaultKeyword));
      const vars = page.body.statements.filter(ts.isVariableStatement).flatMap(s => [...s.declarationList.declarations]);
      stateNames = vars.filter(d => ts.isArrayBindingPattern(d.name)).map(d => d.name.elements[0].name.text);
      const names = vars.filter(d => ts.isIdentifier(d.name)).map(d => d.name.text);
      const ret = page.body.statements.filter(ts.isReturnStatement).at(-1);
      source = source.slice(0, ret.getStart(tree)) + `return {${names.join(",")}, view: (${ret.expression.getText(tree)})};` + source.slice(ret.end);
    }
    const exports = {};
    cache.set(specifier, exports);
    vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText, { exports, require: load, console, localStorage: store, window,
      URLSearchParams, crypto: { randomUUID: () => `practice-${++mount.nextId}` }, Event,
      TextDecoder, AbortController,
      fetch: (url, options) => new Promise((resolve, reject) => requests.push({ url,
        payload: JSON.parse(options.body), reject,
        finish(data) { resolve({ ok: true, json: async () => data, body: { getReader: () => {
          let sent = false;
          return { read: async () => sent ? { done: true } : (sent = true, { done: false,
            value: new TextEncoder().encode(JSON.stringify({ type: "done", paper: data }) + "\n") }) };
        } } }); },
      })),
    }, { filename: path });
    return exports;
  }
  const page = load(`../app/(utility)${route}/page.tsx`).default;
  function render() { slot = 0; stateIndex = 0; api = page(); effects.splice(0).forEach(fn => fn()); return api; }
  render();
  return { get api() { return api; }, state, setters, store, requests, pushes, render,
    get reloads() { return reloads; },
    event: () => window.dispatchEvent({ type: "storage", key: currentKey }),
    resultEvent: () => window.dispatchEvent({ type: "learning-loop-result-change" }),
    unmount: () => slots.forEach(s => s?.cleanup?.()),
  };
}
mount.nextId = 0;

test("grader forwards original passage and context into the real HTTP payload", async () => {
  const store = storage(); seed(store, "first");
  const h = mount("/market/exam-grader", { store });
  assert.equal(h.requests[0]?.payload.passage, "Original reading passage.");
  assert.equal(h.requests[0].payload.subject, "english");
  assert.equal(h.requests[0].payload.kb_name, "english-kb");
  h.requests[0].finish(grade(["inference"])); await flush();
  assert.equal(h.state.stage, "result");
});

for (const subject of ["english", "chinese", "mathematics"]) {
  test(`${subject}: retake restores original entry/KB, generation focus and new submission context`, async () => {
    const store = storage(); seed(store, "first", subject);
    const g = mount("/market/exam-grader", { store });
    g.requests[0].finish(grade(["inference"])); await flush(); g.render(); button(g, "Retake Exam").props.onClick();
    const destination = new URL(g.pushes[0], "http://local");
    assert.equal(destination.pathname, routes[subject]);
    const h = mount(routes[subject], { store, search: destination.search }); await flush(); h.render();
    assert.equal(h.state.kbName, `${subject}-kb`);
    const pending = h.api.handleGenerate();
    assert.equal(h.requests[0].payload.topic_focus, "inference");
    assert.equal(h.requests[0].payload.kb_name, `${subject}-kb`);
    h.requests[0].finish(paper); await pending; h.render();
    h.setters.answers({ q1: "Round two answer" }); h.render(); h.api.handleSubmit();
    const next = JSON.parse(store.getItem(currentKey));
    assert.notEqual(next.id, "first");
    assert.equal(next.subject, subject);
    assert.equal(next.entry, routes[subject]);
    assert.equal(next.kb_name, `${subject}-kb`);
    assert.deepEqual(next.weak_topics, []);
    const second = mount("/market/exam-grader", { store });
    second.requests[0].finish(grade([])); await flush(); second.render(); second.api.goRetake();
    const secondUrl = new URL(second.pushes[0], "http://local");
    const retake = mount(routes[subject], { store, search: secondUrl.search }); await flush(); retake.render();
    const nextPending = retake.api.handleGenerate();
    assert.equal(retake.requests[0].payload.topic_focus, "");
    retake.requests[0].finish(paper); await nextPending;
  });
}

test("cross-subject navigation does not inherit weak topics or the old KB", async () => {
  const store = storage(); seed(store, "old", "chinese", ["classical Chinese"]);
  const h = mount(routes.english, { store }); await flush(); h.render();
  const pending = h.api.handleGenerate();
  assert.equal(h.requests[0].payload.topic_focus, "");
  assert.notEqual(h.requests[0].payload.kb_name, "chinese-kb");
  h.requests[0].finish(paper); await pending; h.render(); h.api.handleSubmit();
  assert.equal(JSON.parse(store.getItem(currentKey)).subject, "english");
});

test("retake with unavailable KB retains its identity and blocks silent replacement", async () => {
  const store = storage(); seed(store, "first");
  const h = mount(routes.english, { store, search: "?practice=first", knowledgeBases: ["unrelated-kb"] });
  await flush(); h.render();
  assert.equal(h.state.kbName, "english-kb");
  await h.api.handleGenerate();
  assert.equal(h.requests.length, 0);
  assert.match(h.state.error, /knowledge base|KB/i);
});

test("out-of-order cross-tab grading cannot overwrite the current practice or show stale result", async () => {
  const store = storage(); seed(store, "old", "english");
  const old = mount("/market/exam-grader", { store });
  seed(store, "new", "chinese");
  const newer = mount("/market/exam-grader", { store });
  newer.requests[0].finish(grade([])); await flush();
  old.requests[0].finish(grade(["STALE"])); await flush();
  assert.equal(old.state.result, null);
  assert.equal(newer.state.stage, "result");
  const flash = mount("/market/flash-deck", { store }); await flush();
  assert.equal(flash.requests.length, 0);
  assert.deepEqual(plain(flash.state.weakTopics), []);
});

test("storage change clears already rendered grading result and prevents old retake", async () => {
  const store = storage(); seed(store, "old");
  const h = mount("/market/exam-grader", { store });
  h.requests[0].finish(grade(["inference"])); await flush(); h.render();
  seed(store, "new", "chinese"); h.event(); h.api.goRetake();
  assert.equal(h.state.result, null);
  assert.equal(h.pushes.length, 0);
});

test("unmounted grading callbacks do not write or show a result", async () => {
  const store = storage(); seed(store, "old");
  const h = mount("/market/exam-grader", { store }); h.unmount();
  h.requests[0].finish(grade(["inference"])); await flush();
  assert.equal(h.state.result, null);
  assert.equal(store.getItem("dtmarket_learning_loop_result:old"), null);
});

test("flashcards use current practice topics and KB, not legacy weak topics", async () => {
  const store = storage(); seed(store, "current", "chinese");
  const g = mount("/market/exam-grader", { store });
  g.requests[0].finish(grade(["inference"])); await flush();
  const h = mount("/market/flash-deck", { store }); await flush();
  assert.deepEqual(h.requests[0]?.payload.topics, ["inference"]);
  assert.equal(h.requests[0].payload.kb_name, "chinese-kb");
  assert.equal(h.state.kbName, "chinese-kb");
  h.requests[0].finish({ cards }); await flush();
  assert.equal(h.state.stage, "review");
});

test("legacy data without context is rejected rather than inventing a subject", async () => {
  const store = storage(); seed(store, "old"); store.removeItem(currentKey);
  const g = mount("/market/exam-grader", { store });
  const h = mount("/market/flash-deck", { store }); await flush();
  assert.equal(g.requests.length, 0);
  assert.equal(h.requests.length, 0);
  assert.match(g.state.error, /start|context/i);
  assert.match(h.state.error, /start|context/i);
});

for (const subject of ["english", "chinese", "mathematics"]) {
test(`${subject}: editing answers and resubmitting creates a fresh immutable submission`, async () => {
  const store = storage();
  const page = mount(routes[subject], { store }); await flush();
  if (subject === "mathematics") page.setters.subject("mathematics");
  page.render();
  const pending = page.api.handleGenerate(); page.requests[0].finish(paper); await pending; page.render();
  page.setters.answers({ q1: "First answer" }); page.render(); page.api.handleSubmit();
  const firstId = JSON.parse(store.getItem(currentKey)).id;
  const first = mount("/market/exam-grader", { store });
  first.requests[0].finish(grade(["OLD WEAK TOPIC"])); await flush();
  page.setters.answers({ q1: "Revised answer" }); page.render(); page.api.handleSubmit();
  assert.notEqual(JSON.parse(store.getItem(currentKey)).id, firstId);
  const second = mount("/market/exam-grader", { store });
  assert.equal(second.requests.length, 1);
  assert.equal(second.requests[0].payload.student_answers.q1, "Revised answer");
  assert.equal(second.state.result, null);
});
}

for (const outcome of ["success", "failure"]) {
  for (const bFinished of [false, true]) {
    test(`same mounted grader: old ${outcome} cannot affect B (${bFinished ? "finished" : "pending"})`, async () => {
      const store = storage(); seed(store, "A");
      const h = mount("/market/exam-grader", { store });
      seed(store, "B", "chinese"); h.event(); h.render();
      assert.equal(h.requests.length, 2);
      if (bFinished) { h.requests[1].finish(grade([])); await flush(); }
      const before = plain(h.state);
      if (outcome === "success") h.requests[0].finish(grade(["OLD"]));
      else h.requests[0].reject(new Error("OLD FAILURE"));
      await flush();
      assert.deepEqual(plain(h.state), before);
      assert.equal(store.getItem("dtmarket_learning_loop_result:A"), null);
      if (!bFinished) { h.requests[1].finish(grade([])); await flush(); }
      assert.equal(h.state.stage, "result");
      assert.equal(h.state.paper.title, "Fixed paper");
      assert.deepEqual(plain(h.state.result.weak_topics), []);
    });
  }
}

test("result commit losing current-id check does not write UI or overwrite B", async () => {
  const store = storage(); seed(store, "A");
  const h = mount("/market/exam-grader", { store });
  const originalSet = store.setItem;
  store.setItem = (key, value) => {
    originalSet(key, value);
    if (key === "dtmarket_learning_loop_result:A") seed(store, "B", "chinese");
  };
  h.requests[0].finish(grade(["OLD"])); await flush();
  assert.equal(h.state.result, null);
  assert.equal(JSON.parse(store.getItem(currentKey)).id, "B");
  const flash = mount("/market/flash-deck", { store }); await flush();
  assert.equal(flash.requests.length, 0);
});

test("flashdeck invalidates active cards when same-window result changes", async () => {
  const store = storage(); seed(store, "A", "english", ["inference"]);
  const listeners = new Map();
  const grader = mount("/market/exam-grader", { store, listeners });
  const h = mount("/market/flash-deck", { store, listeners }); await flush();
  h.requests[0].finish({ cards }); await flush();
  assert.equal(h.state.stage, "review");
  grader.requests[0].finish(grade([])); await flush();
  assert.deepEqual(plain(h.state.cards), []);
  assert.deepEqual(plain(h.state.weakTopics), []);
  assert.notEqual(h.state.stage, "review");
});

test("PaperForge does not invent a subject for a fresh practice", async () => {
  const h = mount(routes.mathematics); await flush(); h.render();
  await h.api.handleGenerate();
  assert.equal(h.requests.length, 0);
  assert.match(h.state.error, /subject/i);
});

test("explicit no-KB retake is preserved after the list loads", async () => {
  const store = storage(); const current = seed(store, "no-kb", "chinese", ["inference"]);
  store.setItem(currentKey, JSON.stringify({ ...current, kb_name: "" }));
  const h = mount(routes.chinese, { store, search: "?practice=no-kb" }); await flush(); h.render();
  assert.equal(h.state.kbName, "");
  const pending = h.api.handleGenerate();
  assert.equal(h.requests[0].payload.kb_name, undefined);
  assert.equal(h.requests[0].payload.topic_focus, "inference");
  h.requests[0].finish(paper); await pending;
});

test("late card result cannot populate another practice's UI or storage", async () => {
  const store = storage(); seed(store, "A", "english", ["inference"]);
  const h = mount("/market/flash-deck", { store }); await flush();
  seed(store, "B", "chinese"); h.event();
  const before = plain(h.state);
  h.requests[0].finish({ cards }); await flush();
  assert.deepEqual(plain(h.state), before);
  assert.equal(store.getItem("dtmarket_flashcards:A"), null);
  assert.equal(store.getItem("dtmarket_flashcards:B"), null);
});

test("FlashDeck recovery button reloads current practice instead of stranding disabled config", async () => {
  const store = storage(); seed(store, "A", "english", ["inference"]);
  const h = mount("/market/flash-deck", { store }); await flush();
  seed(store, "B", "chinese", ["current topic"]); h.event(); h.render();
  const retry = button(h, "Try again") ?? button(h, "Reload practice");
  assert.ok(retry);
  retry.props.onClick();
  assert.equal(h.reloads, 1);
  h.unmount();
  const reloaded = mount("/market/flash-deck", { store }); await flush();
  assert.deepEqual(reloaded.requests[0].payload.topics, ["current topic"]);
  assert.equal(reloaded.requests[0].payload.kb_name, "chinese-kb");
});

test("deleted original KB with empty list still exposes None and sends a no-KB card request", async () => {
  const store = storage(); seed(store, "A", "english", ["inference"]);
  const h = mount("/market/flash-deck", { store, knowledgeBases: [] }); await flush(); h.render();
  const select = elements(h.api.view, n => n.type === "select")[0];
  assert.ok(select, "Original unavailable KB must remain visible/selectable");
  assert.equal(select.props.value, "english-kb");
  const options = elements(select, n => n.type === "option");
  assert.ok(options.some(n => n.props.value === "english-kb"));
  assert.ok(options.some(n => n.props.value === ""));
  assert.equal(h.requests.length, 0);
  select.props.onChange({ target: { value: "" } }); h.render();
  button(h, "Generate Flashcards").props.onClick();
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].payload.kb_name, undefined);
  assert.deepEqual(h.requests[0].payload.topics, ["inference"]);
  h.requests[0].finish({ cards }); await flush();
  assert.equal(h.state.stage, "review");
});
