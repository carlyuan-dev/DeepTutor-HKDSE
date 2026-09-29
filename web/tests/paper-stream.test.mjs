/** Shared paper-generation contract; real API functions with an in-memory HTTP stream. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = readFileSync(new URL("../lib/market-api.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
} }).outputText;

function load(response) {
  const requests = [];
  const exports = {};
  vm.runInNewContext(compiled, {
    exports, TextDecoder,
    require: name => {
      assert.equal(name, "@/lib/api");
      return { apiUrl: path => path };
    },
    fetch: async (url, options) => { requests.push({ url, ...options }); return response; },
  });
  return { api: exports, requests };
}

function stream(text) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({ start(controller) {
    // Single-byte chunks also split Chinese UTF-8 characters and JSON delimiters.
    for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
    controller.close();
  } }));
}

for (const [name, url] of [
  ["generatePaper", "/api/v1/paper-forge/generate"],
  ["generateEnglishPaper", "/api/v1/hkdse/english/generate-paper"],
  ["generateChinesePaper", "/api/v1/hkdse/chinese/generate-paper"],
]) {
  test(`${name}: preserves request and decodes chunked progress/done`, async () => {
    const { api, requests } = load(stream('\n{"type":"progress","message":"准备"}\n{"type":"progress","message":"生成"}\n{"type":"done","paper":{"title":"练习","questions":[]}}\n'));
    const options = { kb_name: "course", topic_focus: "fractions", num_questions: 2 };
    const progress = [];
    const paper = await api[name](options, message => progress.push(message));
    assert.equal(paper.title, "练习");
    assert.equal(paper.questions.length, 0);
    assert.deepEqual(progress, ["准备", "生成"]);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, url);
    assert.equal(requests[0].method, "POST");
    assert.equal(requests[0].headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(requests[0].body), options);
  });

  test(`${name}: forwards server error and rejects HTTP errors`, async () => {
    for (const [response, message] of [
      [stream('{"type":"error","message":"generation failed"}\n'), "generation failed"],
      [new Response("unavailable", { status: 503 }), "Server error 503"],
      [new Response(null), "Server error 200"],
    ]) {
      const { api } = load(response);
      await assert.rejects(api[name]({}, () => {}), { message });
    }
  });

  test(`${name}: preserves missing-done and unterminated-line behavior`, async () => {
    for (const text of ["", '{"type":"progress","message":"working"}\n',
      '{"type":"done","paper":{"title":"unterminated"}}']) {
      const { api } = load(stream(text));
      await assert.rejects(api[name]({}, () => {}), { message: "Stream ended without a paper" });
    }
  });

  test(`${name}: malformed event rejects rather than returning a later paper`, async () => {
    const { api } = load(stream('not json\n{"type":"done","paper":{}}\n'));
    await assert.rejects(api[name]({}, () => {}), error => error.name === "SyntaxError");
  });
}
