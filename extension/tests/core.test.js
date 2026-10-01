const test = require("node:test");
const assert = require("node:assert/strict");

const {
  normalizeWord,
  compactText,
  sentenceFromParts,
  calculatePopupPosition,
  pronunciationView,
  youdaoAudioUrl,
  audioCandidates,
  audioFetchPlan
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

test("pronunciationView keeps exact-form audio and labels a different base form", () => {
  const view = pronunciationView({
    phonetic: "ˈteɪlərɪŋ",
    audioUrl: "https://media.merriam-webster.com/audio/prons/en/us/mp3/t/tailor04.mp3",
    baseWord: "tailor",
    basePhonetic: "ˈteɪlɚ",
    baseAudioUrl: ""
  }, "tailoring");
  assert.equal(view.phonetic, "ˈteɪlərɪŋ");
  assert.match(view.audioUrl, /tailor04\.mp3$/);
  assert.equal(view.speakText, "tailoring");
  assert.deepEqual(view.base, {word: "tailor", phonetic: "ˈteɪlɚ", audioUrl: "", speakText: "tailor"});
});

test("pronunciationView never substitutes base audio when the exact form has none", () => {
  const view = pronunciationView({
    phonetic: "",
    audioUrl: "",
    baseWord: "civilization",
    basePhonetic: "ˌsi-və-lə-ˈzā-shən",
    baseAudioUrl: "https://media.merriam-webster.com/audio/prons/en/us/mp3/c/civili05.mp3"
  }, "civilizations");
  assert.equal(view.audioUrl, "", "main button must fall back to TTS of the selected word");
  assert.equal(view.speakText, "civilizations");
  assert.equal(view.base.word, "civilization");
  assert.match(view.base.audioUrl, /civili05\.mp3$/);
});

test("pronunciationView hides base when it equals the word and accepts snake_case cards", () => {
  assert.equal(pronunciationView({baseWord: "Running"}, "running").base, null);
  const card = pronunciationView({word: "studies", base_word: "study", base_audio_url: "http://insecure/x.mp3"});
  assert.equal(card.speakText, "studies");
  assert.equal(card.base.audioUrl, "", "non-https URLs are ignored");
  assert.equal(pronunciationView(null, "word").audioUrl, "");
});

const MW_TAILORING = "https://media.merriam-webster.com/audio/prons/en/us/mp3/t/tailor04.mp3";
const SERVER = "https://vocab.weixiaocan.com";

test("audioCandidates: exact MW recording first, then server proxy, then Youdao US", () => {
  assert.deepEqual(audioCandidates(MW_TAILORING, "tailoring", SERVER + "/"), [
    MW_TAILORING,
    `${SERVER}/audio/tailoring.mp3`,
    "https://dict.youdao.com/dictvoice?audio=tailoring&type=2"
  ]);
});

test("audioCandidates without exact MW audio goes to the server proxy then Youdao", () => {
  assert.deepEqual(audioCandidates("", "Civilizations", SERVER), [
    `${SERVER}/audio/civilizations.mp3`,
    "https://dict.youdao.com/dictvoice?audio=civilizations&type=2"
  ]);
});

test("audioCandidates still offers Youdao when no server is configured, and ignores non-https MW urls", () => {
  assert.deepEqual(audioCandidates("http://insecure/x.mp3", "went", ""), [
    "https://dict.youdao.com/dictvoice?audio=went&type=2"
  ]);
  assert.deepEqual(audioCandidates("", "", SERVER), [], "nothing to play -> caller uses TTS");
});

test("audio URLs are URL-encoded", () => {
  assert.equal(youdaoAudioUrl("a&type=1#x"), "https://dict.youdao.com/dictvoice?audio=a%26type%3D1%23x&type=2");
  assert.equal(audioCandidates("", "a/b?c", "http://127.0.0.1:8001")[0], "http://127.0.0.1:8001/audio/a%2Fb%3Fc.mp3");
});

test("audioFetchPlan sends the access token only to the configured server", () => {
  assert.deepEqual(audioFetchPlan(`${SERVER}/audio/went.mp3`, SERVER, "tok"), {headers: {"X-Access-Token": "tok"}});
  assert.deepEqual(audioFetchPlan("http://127.0.0.1:8001/audio/went.mp3", "http://127.0.0.1:8001", "tok"),
    {headers: {"X-Access-Token": "tok"}});
  assert.deepEqual(audioFetchPlan("https://dict.youdao.com/dictvoice?audio=went&type=2", SERVER, "tok"), {headers: {}});
  assert.deepEqual(audioFetchPlan(MW_TAILORING, SERVER, "tok"), {headers: {}});
});

test("audioFetchPlan rejects unknown hosts, http and look-alike server URLs", () => {
  assert.equal(audioFetchPlan("https://attacker.example/x.mp3", SERVER, "tok"), null);
  assert.equal(audioFetchPlan("http://dict.youdao.com/dictvoice?audio=went", SERVER, "tok"), null);
  assert.equal(audioFetchPlan("https://vocab.weixiaocan.com.evil.example/audio/x.mp3", SERVER, "tok"), null);
  assert.equal(audioFetchPlan("https://dict.youdao.com.evil.example/x.mp3", SERVER, "tok"), null);
  assert.equal(audioFetchPlan(`${SERVER}/words`, SERVER, "tok"), null);
});
