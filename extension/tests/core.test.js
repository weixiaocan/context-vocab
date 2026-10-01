const test = require("node:test");
const assert = require("node:assert/strict");

const {
  normalizeWord,
  compactText,
  sentenceFromParts,
  calculatePopupPosition
} = require("../core.js");

test("normalizeWord accepts supported English word forms", () => {
  assert.equal(normalizeWord("Hello,"), "hello");
  assert.equal(normalizeWord("state-of-the-art"), "state-of-the-art");
  assert.equal(normalizeWord("don't"), "don't");
  assert.equal(normalizeWord("A"), "a");
});

test("normalizeWord rejects selections that are not one supported word", () => {
  assert.equal(normalizeWord("two words"), "");
  assert.equal(normalizeWord("GPT-5"), "");
  assert.equal(normalizeWord("中文"), "");
  assert.equal(normalizeWord("123"), "");
});

test("compactText normalizes whitespace", () => {
  assert.equal(compactText("  one\n  two\tthree  "), "one two three");
});

test("sentenceFromParts uses the selected occurrence instead of the first occurrence", () => {
  const before = "When building applications, start simple. This might mean not ";
  const after = " agentic systems at all. Agentic systems trade latency for quality.";
  assert.equal(
    sentenceFromParts(before, "building", after),
    "This might mean not building agentic systems at all."
  );
});

test("sentenceFromParts does not insert a space before punctuation", () => {
  assert.equal(
    sentenceFromParts("The result was ", "marginal", ", but still useful."),
    "The result was marginal, but still useful."
  );
});

test("sentenceFromParts limits unpunctuated trailing context", () => {
  const result = sentenceFromParts("Context before ", "tractable", ` ${"x".repeat(400)}`);
  assert.ok(result.length < 280);
  assert.ok(result.startsWith("Context before tractable "));
});

test("calculatePopupPosition keeps a normal popup below the selection", () => {
  const position = calculatePopupPosition({
    selectionRect: {left: 100, top: 100, bottom: 120},
    popupWidth: 320,
    popupHeight: 240,
    viewportWidth: 1000,
    viewportHeight: 800
  });
  assert.deepEqual(position, {left: 100, top: 128});
});

test("calculatePopupPosition flips above near the viewport bottom", () => {
  const position = calculatePopupPosition({
    selectionRect: {left: 100, top: 700, bottom: 720},
    popupWidth: 320,
    popupHeight: 260,
    viewportWidth: 1000,
    viewportHeight: 800
  });
  assert.deepEqual(position, {left: 100, top: 432});
});

test("calculatePopupPosition clamps both horizontal edges", () => {
  const right = calculatePopupPosition({
    selectionRect: {left: 950, top: 100, bottom: 120},
    popupWidth: 320,
    popupHeight: 200,
    viewportWidth: 1000,
    viewportHeight: 800
  });
  const left = calculatePopupPosition({
    selectionRect: {left: -20, top: 100, bottom: 120},
    popupWidth: 320,
    popupHeight: 200,
    viewportWidth: 1000,
    viewportHeight: 800
  });
  assert.equal(right.left, 668);
  assert.equal(left.left, 12);
});

const {
  escapeHtml,
  sentenceTranslation,
  collectButtonView,
  initialCollectStatus
} = require("../core.js");

test("escapeHtml escapes markup characters and tolerates empty values", () => {
  assert.equal(escapeHtml(`<img src=x onerror="a('b')">&`), "&lt;img src=x onerror=&quot;a(&#039;b&#039;)&quot;&gt;&amp;");
  assert.equal(escapeHtml(undefined), "");
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(0), "0");
});

test("sentenceTranslation returns compact trans_zh unless it repeats the word meaning", () => {
  assert.equal(sentenceTranslation({answer_zh: "冗长的", trans_zh: "  指令\n更冗长。 "}), "指令 更冗长。");
  assert.equal(sentenceTranslation({answer_zh: "冗长的", trans_zh: "冗长的"}), "");
  assert.equal(sentenceTranslation({answer_zh: "冗长的"}), "");
  assert.equal(sentenceTranslation(null), "");
});

test("collectButtonView maps every collect status to a label and disabled flag", () => {
  assert.deepEqual(collectButtonView("idle"), {label: "加入生词本", disabled: false, tone: "primary"});
  assert.deepEqual(collectButtonView("saving"), {label: "加入中…", disabled: true, tone: "busy"});
  assert.deepEqual(collectButtonView("saved"), {label: "✓ 已加入生词本", disabled: true, tone: "done"});
  assert.deepEqual(collectButtonView("exists"), {label: "✓ 已在生词本", disabled: true, tone: "done"});
  assert.deepEqual(collectButtonView("error"), {label: "重试加入", disabled: false, tone: "retry"});
  assert.equal(collectButtonView("unknown").label, "加入生词本");
});

test("initialCollectStatus uses the lookup collected flag", () => {
  assert.equal(initialCollectStatus({collected: true}), "exists");
  assert.equal(initialCollectStatus({collected: false}), "idle");
  assert.equal(initialCollectStatus(null), "idle");
});
