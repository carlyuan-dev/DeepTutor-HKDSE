/**
 * Focused source-executing audit; no React DOM, HTTP, LLM, or speech engine.
 * AST instrumentation only exposes the page's closures in place of its JSX return.
 * Production callbacks/guards/prefetch/caption timers are executed unchanged.
 * Hook state is a single-render harness: this is NOT a browser lifecycle/E2E test.
 * Run: node --test web/tests/oral-practice-races.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const pageUrl = new URL("../app/(utility)/market/hkdse/english/oral-practice/page.tsx", import.meta.url);
const source = readFileSync(pageUrl, "utf8");
const tree = ts.createSourceFile("page.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const page = tree.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === "OralPracticePage");
assert.ok(page?.body);
const declarations = page.body.statements.filter(ts.isVariableStatement).flatMap(s => [...s.declarationList.declarations]);
const refs = declarations.filter(d => ts.isIdentifier(d.name) && d.name.text.endsWith("Ref")).map(d => d.name.text);
const stateNames = declarations.filter(d => ts.isArrayBindingPattern(d.name)).map(d => d.name.elements[0].name.text);
const pageReturn = page.body.statements.filter(ts.isReturnStatement).at(-1);
assert.ok(pageReturn);
const exposed = ["sendAiTurn", "enterPartB", "prefetchNextAiTurn", "handleNewPractice",
  "prefetchFromPartialUserTranscript", "submitUserTurn", "transcriptLooksCompatible",
  "scheduleNextAiTurn", "abortActiveAiTurn", "clearPreparedAiTurn", "revealAiMessageText", ...refs];
const edits = [{ start: pageReturn.getStart(tree), end: pageReturn.end, text: `return {${exposed.join(",")}};` }];
const imported = [];
for (const node of tree.statements.filter(ts.isImportDeclaration)) {
  if (node.importClause?.name) imported.push(node.importClause.name.text);
  if (node.importClause?.namedBindings && ts.isNamedImports(node.importClause.namedBindings)) {
    imported.push(...node.importClause.namedBindings.elements.map(e => e.name.text));
  }
  edits.push({ start: node.getStart(tree), end: node.end, text: "" });
}
let instrumented = source;
for (const edit of edits.sort((a, b) => b.start - a.start)) {
  instrumented = instrumented.slice(0, edit.start) + edit.text + instrumented.slice(edit.end);
}
const compiled = ts.transpileModule(instrumented, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;

function mount({ speech = false } = {}) {
  const spoken = [];
  const state = {}, effects = [], requests = [], timers = new Map();
  let stateIndex = 0, timerId = 0, now = 0;
  const timer = (callback, delay, repeat) => {
    const id = ++timerId;
    timers.set(id, { callback, delay, repeat, due: now + delay });
    return id;
  };
  const context = {
    ...Object.fromEntries(imported.map(name => [name, () => {}])),
    exports: {}, require: () => ({ jsx: () => null, jsxs: () => null }),
    AbortController, console,
    useState(initial) {
      const name = stateNames[stateIndex++];
      state[name] = typeof initial === "function" ? initial() : initial;
      return [state[name], value => { state[name] = typeof value === "function" ? value(state[name]) : value; }];
    },
    useRef: current => ({ current }),
    useEffect: (callback, deps) => effects.push({ callback, deps }),
    setTimeout: (cb, delay) => timer(cb, delay, false),
    setInterval: (cb, delay) => timer(cb, delay, true),
    clearTimeout: id => timers.delete(id), clearInterval: id => timers.delete(id),
    takeOralTurn: (payload, callbacks, options) => new Promise(resolve => {
      requests.push({ payload, callbacks, signal: options.signal, resolve });
    }),
    // No speech engine in this harness. Text-mode promises use the actual branch.
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    window: speech ? { speechSynthesis: {
      cancel() {}, speak(utterance) { spoken.push(utterance.text); },
    } } : {},
  };
  vm.runInNewContext(compiled, context, { filename: pageUrl.pathname });
  const api = context.exports.default();
  const cleanups = effects.map(e => e.callback()).filter(f => typeof f === "function");
  const tick = async (duration) => {
    const end = now + duration;
    for (let count = 0; count < 2000; count++) {
      const next = [...timers].filter(([, t]) => t.due <= end).sort((a, b) => a[1].due - b[1].due)[0];
      if (!next) break;
      const [id, t] = next;
      now = t.due;
      if (t.repeat) t.due += t.delay; else timers.delete(id);
      t.callback();
      await flush();
      if (count === 1999) throw new Error("Timer runaway");
    }
    now = end;
    await flush();
  };
  return { api, state, requests, timers, tick, spoken, unmount: () => cleanups.forEach(f => f()),
    finish(index, content) {
      const request = requests[index];
      // Intentionally deliver callbacks even after abort, to test page defenses.
      request.callbacks.onChunk(content);
      request.callbacks.onTurnEnd({ content, speaker: request.payload.speaker });
      request.resolve();
    },
  };
}

async function flush() { for (let i = 0; i < 8; i++) await Promise.resolve(); }
function discussion(h) {
  h.api.topicIdRef.current = "test-topic";
  h.api.topicRef.current = { topic_id: "test-topic", guiding_questions: ["Discuss school libraries."] };
  h.api.modeRef.current = "text";
  h.api.aiQueueRef.current = ["candidate_a", "candidate_b", "candidate_c"];
  h.api.partBQuestionRef.current = "What is your view?";
}
const texts = h => Array.from(h.api.messagesRef.current, m => m.content);

test("Part A → B: old active stream and queued continuation cannot write or reschedule", async () => {
  const h = mount(); discussion(h);
  const pending = h.api.sendAiTurn("candidate_a", [], 0);
  h.api.scheduleNextAiTurn([]);
  h.api.enterPartB(h.api.messagesRef.current);
  assert.equal(h.requests[0].signal.aborted, true);
  const expected = texts(h);
  assert.equal(expected.length, 1);
  assert.equal(h.api.phaseRef.current, "individual_response");
  h.finish(0, "STALE PART A");
  h.requests[0].callbacks.onError("STALE ERROR");
  await pending; await h.tick(7000);
  assert.deepEqual(texts(h), expected);
  assert.equal(h.api.streamingRef.current, "");
  assert.equal(h.state.error, "");
  assert.equal(h.requests.length, 1);
});

test("reverse completion: old request cannot overwrite new turn or clear its controller", async () => {
  const h = mount(); discussion(h);
  const older = h.api.sendAiTurn("candidate_a", [], 0);
  const newer = h.api.sendAiTurn("candidate_b", [], 0);
  const current = h.api.activeAiTurnAbortRef.current;
  assert.equal(h.requests[0].signal.aborted, true);
  h.requests[0].callbacks.onError("OLD ERROR");
  assert.equal(h.api.activeAiTurnAbortRef.current, current);
  h.finish(1, "NEW TURN"); await newer; await h.tick(300);
  h.finish(0, "OLD TURN"); await older; await flush();
  assert.deepEqual(texts(h), ["NEW TURN"]);
  assert.equal(h.state.error, "");
});

test("prefetch: reverse completion cannot replace current prepared turn; Part B discards late result", async () => {
  const h = mount(); discussion(h);
  h.api.prefetchNextAiTurn([]);
  h.api.aiQueueRef.current = ["candidate_b", "candidate_c"];
  h.api.prefetchNextAiTurn([]);
  h.finish(1, "NEW PREFETCH"); await flush();
  h.finish(0, "OLD PREFETCH"); await flush();
  assert.equal(h.api.preparedAiTurnRef.current.content, "NEW PREFETCH");
  h.api.clearPreparedAiTurn();
  h.api.prefetchNextAiTurn([]);
  h.api.enterPartB(h.api.messagesRef.current);
  h.finish(2, "LATE PREFETCH"); await flush();
  assert.equal(h.api.preparedAiTurnRef.current, null);
  assert.equal(texts(h).some(t => /PREFETCH/.test(t)), false);
});

test("caption already playing: Part B cancels caption writes and does not resume old speaker", async () => {
  const h = mount(); discussion(h);
  const pending = h.api.sendAiTurn("candidate_a", [], 0);
  h.finish(0, "OLD WORDS STILL BEING DISPLAYED"); await pending;
  await h.tick(115);
  assert.ok(h.api.aiCaptionTimerRef.current);
  const requestCount = h.requests.length;
  h.api.enterPartB(h.api.messagesRef.current);
  const expected = texts(h);
  await h.tick(7000);
  assert.deepEqual(texts(h), expected);
  assert.equal(h.api.aiCaptionTimerRef.current, null);
  assert.equal(h.requests.length, requestCount);
});

test("current request failure enters error state; no automatic retry is started", async () => {
  const h = mount(); discussion(h);
  const pending = h.api.sendAiTurn("candidate_a", [], 0);
  h.requests[0].callbacks.onError("Server error 503"); h.requests[0].resolve();
  await pending; await h.tick(7000);
  assert.equal(h.state.stage, "error");
  assert.equal(h.state.error, "Server error 503");
  assert.equal(h.state.isAiSpeaking, false);
  assert.equal(h.requests.length, 1);
});

test("fresh mount starts at config with empty history, not resumed practice", () => {
  const old = mount(); discussion(old);
  old.api.messagesRef.current = [{ speaker: "candidate_a", content: "OLD SESSION" }];
  old.unmount();
  const fresh = mount();
  assert.equal(fresh.state.stage, "config");
  assert.equal(fresh.api.topicIdRef.current, "");
  assert.deepEqual(texts(fresh), []);
  assert.equal(fresh.requests.length, 0);
});

// Regression tests execute the real control path through consumption/display.
// The speech boundary records the real speakAiMessage -> speechSynthesis.speak call;
// it does not simulate audible playback. Keep speech pending to avoid later turns.
const partialView = "I support keeping school libraries open every evening for students";
const reversedView = "I do not support keeping school libraries open every evening for students";
const unrelatedView = "Instead I oppose spending money because staffing costs exceed educational benefits";
test("prefetch final-text audit: agenda-state transition aborts in-flight reply", async () => {
  const h = mount({ speech: true }); discussion(h);
  h.api.modeRef.current = "voice";
  h.api.messagesRef.current = [{ speaker: "candidate_b", content: "Please share your opinion." }];
  h.api.prefetchFromPartialUserTranscript(partialView);
  await h.api.submitUserTurn({ speaker: "candidate_d", content: reversedView });
  assert.equal(h.requests[0].signal.aborted, true);
  h.finish(0, "STALE REPLY"); await flush();
  assert.equal(h.api.preparedAiTurnRef.current, null);
  await h.tick(1100);
  assert.deepEqual(h.spoken, []);
  assert.equal(texts(h).includes("STALE REPLY"), false);
  assert.equal(h.requests[1].payload.history.at(-1).content, reversedView);
  h.unmount();
});
for (const scenario of [
  { name: "in-flight opposite stance is invalidated", final: reversedView, ready: false, compatible: false, consumed: false },
  { name: "in-flight consistent transcript is consumed (positive control)", final: partialView, ready: false, compatible: true, consumed: true },
  { name: "completed opposite stance is invalidated", final: reversedView, ready: true, compatible: false, consumed: false },
  { name: "completed consistent transcript is reused", final: partialView, ready: true, compatible: true, consumed: true },
  { name: "completed low-overlap cache is invalidated (negative control)", final: unrelatedView, ready: true, compatible: false, consumed: false },
  { name: "in-flight low-overlap reply is invalidated", final: unrelatedView, ready: false, compatible: false, consumed: false },
]) {
  test(`prefetch final-text audit: ${scenario.name}`, async () => {
    const h = mount({ speech: true }); discussion(h);
    h.api.topicRef.current.guiding_questions = ["Opening hours"];
    h.api.modeRef.current = "voice";
    // Existing discussion, same agenda, no agenda-transition phrase: isolate text
    // changes from a role/agenda change that would independently invalidate cache.
    h.api.messagesRef.current = [{ speaker: "candidate_b", content: "Please share your opinion." }];
    const generated = "You support evening opening; I agree with your position.";
    assert.equal(h.api.transcriptLooksCompatible(partialView, scenario.final), scenario.compatible);
    h.api.prefetchFromPartialUserTranscript(partialView);
    assert.equal(h.requests.length, 1);
    assert.equal(h.requests[0].payload.history.at(-1).content, partialView);
    if (scenario.ready) { h.finish(0, generated); await flush(); }
    else assert.equal(h.api.preparedAiTurnRef.current, null);

    await h.api.submitUserTurn({ speaker: "candidate_d", content: scenario.final });
    assert.equal(texts(h).at(-1), scenario.final);
    if (!scenario.ready) {
      assert.equal(h.requests[0].signal.aborted, !scenario.consumed);
      h.finish(0, generated); await flush();
    }
    assert.equal(h.api.preparedAiTurnRef.current?.content ?? null, scenario.consumed ? generated : null);
    // Let submitUserTurn's REAL scheduleNextAiTurn timer call sendAiTurn,
    // preparedMatchesPlan, commitAiTurn, caption scheduling and speakAiMessage.
    await h.tick(1100);
    assert.equal(h.api.preparedAiTurnRef.current, null);
    if (scenario.consumed) {
      assert.deepEqual(h.spoken, [generated]);
      assert.ok(h.api.aiCaptionTimerRef.current);
      // The extra request is next-speaker background prefetch, NOT regeneration
      // of the consumed candidate_a reply against final user input.
      assert.equal(h.requests[1].payload.speaker, "candidate_b");
      await h.tick(115 * 20);
      assert.equal(texts(h).at(-1), generated);
      assert.equal(h.state.messages.at(-1).content, generated);
      assert.ok(texts(h).includes(scenario.final));
    } else {
      assert.deepEqual(h.spoken, []);
      assert.equal(h.requests[1].payload.speaker, "candidate_a");
      assert.equal(h.requests[1].payload.history.at(-1).content, scenario.final);
      assert.equal(texts(h).includes(generated), false);
    }
    h.unmount();
  });
}

for (const oldFinishesFirst of [true, false]) {
  test(`partial prefetch stale completion cannot affect new input (${oldFinishesFirst ? "new pending" : "new cached"})`, async () => {
    const h = mount({ speech: true }); discussion(h);
    h.api.modeRef.current = "voice";
    h.api.topicRef.current.guiding_questions = ["Opening hours"];
    h.api.messagesRef.current = [{ speaker: "candidate_b", content: "Your view?" }];
    h.api.prefetchFromPartialUserTranscript(partialView);
    await h.api.submitUserTurn({ speaker: "candidate_d", content: reversedView });
    h.api.prefetchFromPartialUserTranscript(reversedView);
    const currentController = h.api.prefetchAbortRef.current;
    assert.equal(h.requests[0].signal.aborted, true);
    await h.api.submitUserTurn({ speaker: "candidate_d", content: reversedView });
    if (oldFinishesFirst) {
      h.finish(0, "OLD"); await flush();
      assert.equal(h.api.prefetchAbortRef.current, currentController);
      assert.equal(h.api.preparedAiTurnRef.current, null);
    }
    h.finish(1, "NEW VALID INPUT"); await flush();
    const validCache = h.api.preparedAiTurnRef.current;
    if (!oldFinishesFirst) { h.finish(0, "OLD"); await flush(); }
    assert.equal(h.api.preparedAiTurnRef.current, validCache);
    assert.equal(currentController.signal.aborted, false);
    await h.tick(1100 + 115 * 4);
    assert.deepEqual(h.spoken, ["NEW VALID INPUT"]);
    assert.equal(texts(h).at(-1), "NEW VALID INPUT");
    h.unmount();
  });
}
