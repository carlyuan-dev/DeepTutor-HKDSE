import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../app/(utility)/market/hkdse/english/essay-coach/page.tsx', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;

function render(states, api = {}) {
  const exports = {};
  let index = 0;
  vm.runInNewContext(code, { exports, require: (name) => {
    if (name === 'react') return { ...React, useState: (initial) => [index < states.length ? states[index++] : initial, () => {}] };
    if (name === 'next/link') return { default: 'a' };
    if (name === 'lucide-react') return { ArrowLeft: () => null, FileText: () => null, Loader2: () => null };
    if (name === '@/lib/market-api') return api;
    return require(name);
  }});
  return exports.default();
}

test('result renders rater disagreement and manual review warning', () => {
  const dimension = { score: 4, max_score: 7, comment: 'Evidence', individual_scores: [0, 7, 4] };
  const result = {
    content: dimension, language: dimension, organisation: dimension,
    total_score: 12, max_score: 21, percentage: 57.1,
    strengths: [], improvements: [], overall_comment: 'Review',
    ensemble: { overall_agreement: 50, review_recommended: true, agreement_level: 'low' },
  };
  const states = ['result', '', '', 'argument', result, ''];
  const html = renderToStaticMarkup(render(states));
  assert.match(html, /Rater agreement/);
  assert.match(html, /50/);
  assert.match(html, /Manual review recommended/);
  assert.match(html, /Strict.*0.*Lenient.*7.*Balanced.*4/s);
  assert.match(html, /not a probability of correctness/);
});

test('incomplete review clearly displays balanced fallback without agreement', () => {
  const d = {score: 4, max_score: 7, comment: 'Evidence'};
  const result = {content:d, language:d, organisation:d, total_score:12, max_score:21,
    strengths:[], improvements:[], percentage:57.1, overall_comment:'Original',
    grading:{review_status:'incomplete', strategy_used:'balanced', request_id:'req-local', failures:[]}};
  const html = renderToStaticMarkup(render(['result','','','argument',result,'']));
  assert.match(html, /Review incomplete/);
  assert.match(html, /balanced score/i);
  assert.doesNotMatch(html, /Rater agreement/);
});

for (const mode of ['single', 'review']) {
  test(`submit sends explicit ${mode} mode`, async () => {
    let request;
    const tree = render(['config','Title','Essay','argument',null,'',mode], {
      gradeEnglishEssay: async (r) => { request = r; return {}; },
    });
    function find(node) {
      if (!node || typeof node !== 'object') return null;
      if (node.type === 'button' && node.props.children === 'Grade Essay') return node;
      for (const child of React.Children.toArray(node.props?.children)) {
        const found = find(child); if (found) return found;
      }
      return null;
    }
    await find(tree).props.onClick();
    assert.equal(request.mode, mode);
    const html = renderToStaticMarkup(tree);
    assert.match(html, /Balanced only/);
    assert.match(html, /Three-rater review/);
  });
}

test('retryable error exposes a manual retry action', () => {
  const html = renderToStaticMarkup(render(['error','','Essay','argument',null,'Failed','review',true]));
  assert.match(html, /Retry grading/);
});
