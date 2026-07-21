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

  return {normalizeWord, compactText, sentenceFromParts, calculatePopupPosition};
});
