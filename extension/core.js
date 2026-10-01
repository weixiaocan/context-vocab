(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.VocabCardCore = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function normalizeWord(text) {
    if (!text || /\s/.test(text)) return "";
    const word = text.replace(/^[^A-Za-z0-9]+|[^A-Za-z0-9]+$/g, "").toLowerCase();
    return /^[a-z][a-z'-]{0,78}[a-z]$|^[a-z]$/.test(word) ? word : "";
  }

  function compactText(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function sentenceFromParts(beforeText, selectedText, afterText, maxLength = 2000) {
    const before = compactText(beforeText);
    const selected = compactText(selectedText);
    const after = compactText(afterText);
    const start = Math.max(
      before.lastIndexOf("."),
      before.lastIndexOf("?"),
      before.lastIndexOf("!"),
      before.lastIndexOf(";")
    ) + 1;
    const endCandidates = [after.indexOf("."), after.indexOf("?"), after.indexOf("!"), after.indexOf(";")]
      .filter(pos => pos >= 0);
    const beforePart = before.slice(start).trimStart();
    const afterEnd = endCandidates.length ? Math.min(...endCandidates) + 1 : Math.min(after.length, 240);
    const afterPart = after.slice(0, afterEnd).trimEnd();
    const afterSeparator = /^[,.:;!?]/.test(afterPart) ? "" : " ";
    return compactText(`${beforePart} ${selected}${afterSeparator}${afterPart}`).slice(0, maxLength);
  }

  function calculatePopupPosition({
    selectionRect,
    popupWidth,
    popupHeight,
    scrollX = 0,
    scrollY = 0,
    viewportWidth,
    viewportHeight,
    margin = 12,
    gap = 8
  }) {
    const preferredLeft = selectionRect ? selectionRect.left + scrollX : scrollX + 24;
    const maxLeft = scrollX + viewportWidth - popupWidth - margin;
    const left = Math.max(scrollX + margin, Math.min(preferredLeft, maxLeft));

    let top = selectionRect ? selectionRect.bottom + scrollY + gap : scrollY + 80;
    const viewportBottom = scrollY + viewportHeight - margin;
    if (selectionRect && top + popupHeight > viewportBottom) {
      top = selectionRect.top + scrollY - popupHeight - gap;
    }
    top = Math.max(scrollY + margin, top);
    return {left, top};
  }

  function escapeHtml(text) {
    return String(text ?? "").replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[ch]));
  }

  // Sentence translation worth showing: non-empty and not just the word meaning again.
  function sentenceTranslation(entry) {
    const trans = compactText(entry?.trans_zh);
    if (!trans) return "";
    if (trans === compactText(entry?.answer_zh)) return "";
    return trans;
  }

  // View model for the "add to vocab" button. status: idle | saving | saved | exists | error
  function collectButtonView(status) {
    switch (status) {
      case "saving":
        return {label: "加入中…", disabled: true, tone: "busy"};
      case "saved":
        return {label: "✓ 已加入生词本", disabled: true, tone: "done"};
      case "exists":
        return {label: "✓ 已在生词本", disabled: true, tone: "done"};
      case "error":
        return {label: "重试加入", disabled: false, tone: "retry"};
      default:
        return {label: "加入生词本", disabled: false, tone: "primary"};
    }
  }

  function initialCollectStatus(entry) {
    return entry?.collected ? "exists" : "idle";
  }

  return {
    normalizeWord,
    compactText,
    sentenceFromParts,
    calculatePopupPosition,
    escapeHtml,
    sentenceTranslation,
    collectButtonView,
    initialCollectStatus
  };
});
