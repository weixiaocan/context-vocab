(function () {
  let popup = null;
  let lastSelection = null;

  document.addEventListener("mouseup", () => {
    window.setTimeout(handleSelection, 20);
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") removePopup();
  });

  async function handleSelection() {
    const selection = window.getSelection();
    const raw = selection ? selection.toString().trim() : "";
    const word = normalizeWord(raw);
    if (!word) return;

    const range = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
    const rect = range ? range.getBoundingClientRect() : null;
    lastSelection = {
      word,
      sentence: findSentence(selection.anchorNode, word),
      sourceUrl: location.href
    };

    showPopup(rect, word, {loading: true});
    try {
      const result = await window.VocabCardApi.lookupWord(word);
      showPopup(rect, word, {entry: result});
    } catch (error) {
      showPopup(rect, word, {error: "查词失败"});
    }
  }

  function normalizeWord(text) {
    if (!text || /\s/.test(text)) return "";
    const word = text.replace(/^[^A-Za-z]+|[^A-Za-z]+$/g, "").toLowerCase();
    return /^[a-z][a-z'-]{0,78}[a-z]$|^[a-z]$/.test(word) ? word : "";
  }

  function findSentence(anchorNode, word) {
    const container = anchorNode && anchorNode.nodeType === Node.TEXT_NODE
      ? anchorNode.parentElement
      : anchorNode;
    const text = (container && container.innerText) || document.body.innerText || "";
    const compact = text.replace(/\s+/g, " ").trim();
    const index = compact.toLowerCase().indexOf(word.toLowerCase());
    if (index < 0) return compact.slice(0, 500);

    const before = compact.slice(0, index);
    const after = compact.slice(index);
    const start = Math.max(
      before.lastIndexOf("."),
      before.lastIndexOf("?"),
      before.lastIndexOf("!"),
      before.lastIndexOf(";")
    ) + 1;
    const endCandidates = [after.indexOf("."), after.indexOf("?"), after.indexOf("!"), after.indexOf(";")]
      .filter(pos => pos >= 0);
    const end = endCandidates.length ? index + Math.min(...endCandidates) + 1 : Math.min(compact.length, index + 240);
    return compact.slice(start, end).trim();
  }

  function showPopup(rect, word, state) {
    removePopup();
    popup = document.createElement("div");
    popup.className = "vocab-card-popup";
    const top = rect ? rect.bottom + window.scrollY + 8 : window.scrollY + 80;
    const left = rect ? Math.min(rect.left + window.scrollX, window.scrollX + window.innerWidth - 330) : window.scrollX + 24;
    popup.style.top = `${Math.max(top, 12)}px`;
    popup.style.left = `${Math.max(left, 12)}px`;

    if (state.loading) {
      popup.innerHTML = `<div class="vocab-card-title">${escapeHtml(word)}</div><div class="vocab-card-muted">查词中...</div>`;
    } else if (state.error) {
      popup.innerHTML = popupHtml(word, `<div class="vocab-card-muted">${state.error}</div>`);
    } else if (!state.entry) {
      popup.innerHTML = popupHtml(word, `<div class="vocab-card-muted">查不到</div>`);
    } else {
      const entry = state.entry;
      popup.innerHTML = popupHtml(word, `
        <div class="vocab-card-meta">${escapeHtml(entry.phonetic || "")} ${escapeHtml(entry.partOfSpeech || "")}</div>
        <ol>${entry.definitions.map(def => `<li>${escapeHtml(def)}</li>`).join("") || "<li>暂无释义</li>"}</ol>
        <div class="vocab-card-actions">
          ${entry.audioUrl ? `<button data-action="play">发音</button>` : ""}
          <button data-action="collect">加入生词本</button>
        </div>
        <div class="vocab-card-status"></div>
      `);
      popup.querySelector('[data-action="play"]')?.addEventListener("click", () => {
        new Audio(entry.audioUrl).play().catch(() => {});
      });
      popup.querySelector('[data-action="collect"]')?.addEventListener("click", collectCurrentWord);
    }

    document.body.appendChild(popup);
  }

  function popupHtml(word, body) {
    return `
      <button class="vocab-card-close" type="button" aria-label="Close">×</button>
      <div class="vocab-card-title">${escapeHtml(word)}</div>
      ${body}
    `;
  }

  async function collectCurrentWord() {
    if (!lastSelection || !popup) return;
    const status = popup.querySelector(".vocab-card-status");
    status.textContent = "入库中...";
    try {
      await window.VocabCardApi.collectWord(lastSelection);
      status.textContent = "已加入";
    } catch (error) {
      status.textContent = "入库失败";
    }
  }

  document.addEventListener("click", event => {
    if (event.target.classList && event.target.classList.contains("vocab-card-close")) {
      removePopup();
    }
  });

  function removePopup() {
    if (popup) {
      popup.remove();
      popup = null;
    }
  }

  function escapeHtml(text) {
    return String(text || "").replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[ch]));
  }
})();
