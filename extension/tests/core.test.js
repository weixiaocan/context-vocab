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
