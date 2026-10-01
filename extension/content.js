(function () {
  const {
    normalizeWord,
    sentenceFromParts,
    calculatePopupPosition,
    escapeHtml,
    sentenceTranslation,
    collectButtonView,
    initialCollectStatus
  } = window.VocabCardCore;
  let popup = null;
  let lastSelection = null;
  let lookupRequestId = 0;

  document.addEventListener("mouseup", event => {
    if (event.target.closest?.(".vocab-card-popup")) return;
    window.setTimeout(handleSelection, 20);
  }, true);

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") dismissPopup();
  });

  async function handleSelection() {
    const selection = window.getSelection();
    const raw = selection ? selection.toString().trim() : "";
    const word = normalizeWord(raw);
    if (!word) return;
    const requestId = ++lookupRequestId;

    const range = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
    const rect = range ? range.getBoundingClientRect() : null;
    lastSelection = {
      word,
      sentence: findSentence(selection),
      sourceUrl: location.href
    };

    showPopup(rect, word, {loading: true});
    try {
      const result = await window.VocabCardApi.lookupWord(word, lastSelection.sentence);
      if (requestId !== lookupRequestId) return;
      lastSelection.dictionaryEntry = result;
      showPopup(rect, word, {entry: result});
    } catch (error) {
      if (requestId !== lookupRequestId) return;
      showPopup(rect, word, {error: lookupErrorMessage(error)});
    }
  }

  function findSentence(selection) {
    if (!selection?.rangeCount) return "";
    const range = selection.getRangeAt(0);
    const startElement = range.startContainer.nodeType === Node.TEXT_NODE
      ? range.startContainer.parentElement
      : range.startContainer;
    const container = startElement?.closest?.("p, li, blockquote, td, th, figcaption, pre, div")
      || startElement
      || document.body;

    const beforeRange = document.createRange();
    beforeRange.selectNodeContents(container);
    beforeRange.setEnd(range.startContainer, range.startOffset);
    const afterRange = document.createRange();
    afterRange.selectNodeContents(container);
    afterRange.setStart(range.endContainer, range.endOffset);

    return sentenceFromParts(beforeRange.toString(), range.toString(), afterRange.toString());
  }

  function showPopup(rect, word, state) {
    removePopup();
    popup = document.createElement("div");
    popup.className = "vocab-card-popup";
    popup.lang = "zh-CN";
    popup.style.visibility = "hidden";

    if (state.loading) {
      popup.innerHTML = popupHtml(word, `<div class="vocab-card-muted">查词中…</div>`);
    } else if (state.error) {
      popup.innerHTML = popupHtml(word, `<div class="vocab-card-muted">${escapeHtml(state.error)}</div>`);
    } else if (!state.entry) {
      popup.innerHTML = popupHtml(word, `<div class="vocab-card-muted">查不到</div>`);
    } else {
      const entry = state.entry;
      const audioButton = `<button class="vocab-card-audio" type="button" data-action="play" aria-label="播放 ${escapeHtml(word)} 的发音" title="${entry.audioUrl ? "音频加载中" : "使用浏览器语音播放"}" ${entry.audioUrl ? "disabled" : ""}>🔊</button>`;
      popup.innerHTML = popupHtml(word, entryBodyHtml(entry), audioButton);
      bindAudio(word, entry);
      setCollectStatus(initialCollectStatus(entry));
      popup.querySelector('[data-action="collect"]')?.addEventListener("click", collectCurrentWord);
    }

    document.body.appendChild(popup);
    positionPopup(rect);
    popup.style.visibility = "visible";
  }

  function entryBodyHtml(entry) {
    const metaParts = [];
    if (entry.phonetic) metaParts.push(`<span class="vocab-card-phonetic" lang="en">${escapeHtml(entry.phonetic)}</span>`);
    if (entry.partOfSpeech) metaParts.push(`<span class="vocab-card-pos" lang="en">${escapeHtml(entry.partOfSpeech)}</span>`);
    const meta = metaParts.length ? `<div class="vocab-card-meta">${metaParts.join("")}</div>` : "";

    const definitions = (entry.definitions || []).filter(Boolean);
    const englishList = definitions.length
      ? `<ol lang="en">${definitions.map(def => `<li>${escapeHtml(def)}</li>`).join("")}</ol>`
      : `<div class="vocab-card-muted" lang="zh-CN">暂无英文释义</div>`;
    const actions = `
      <div class="vocab-card-actions">
        <button type="button" class="vocab-card-collect" lang="zh-CN" data-action="collect"></button>
      </div>
      <div class="vocab-card-error" lang="zh-CN" role="alert" hidden></div>
      <div class="vocab-card-status" aria-live="polite"></div>
    `;

    if (entry.answer_zh) {
      const trans = sentenceTranslation(entry);
      const transBlock = trans
        ? `<div class="vocab-card-trans" lang="zh-CN">
             <div class="vocab-card-label">整句翻译</div>
             <div class="vocab-card-trans-text">${escapeHtml(trans)}</div>
           </div>`
        : "";
      const countLabel = definitions.length ? `<span class="vocab-card-count">${definitions.length}</span>` : "";
      return `
        ${meta}
        <div class="vocab-card-zh" lang="zh-CN">${escapeHtml(entry.answer_zh)}</div>
        ${transBlock}
        <details class="vocab-card-en">
          <summary>
            <span lang="zh-CN">英文释义</span>${countLabel}
            <span class="vocab-card-hint" lang="zh-CN" aria-hidden="true"></span>
            <svg class="vocab-card-chevron" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </summary>
          ${englishList}
        </details>
        ${actions}
      `;
    }

    return `
      ${meta}
      <div class="vocab-card-en-plain">${englishList}</div>
      ${actions}
    `;
  }

  function setCollectStatus(status, errorText = "") {
    const button = popup?.querySelector('[data-action="collect"]');
    if (!button) return;
    const view = collectButtonView(status);
    button.disabled = view.disabled;
    button.dataset.tone = view.tone;
    button.setAttribute("aria-busy", status === "saving" ? "true" : "false");
    button.innerHTML = status === "saving"
      ? `<span class="vocab-card-spinner" aria-hidden="true"></span>${escapeHtml(view.label)}`
      : escapeHtml(view.label);
    const error = popup.querySelector(".vocab-card-error");
    if (error) {
      error.textContent = status === "error" ? errorText : "";
      error.hidden = status !== "error";
    }
  }

  function bindAudio(word, entry) {
    const playButton = popup.querySelector('[data-action="play"]');
    if (!playButton) return;
    if (!entry.audioUrl) {
      playButton.addEventListener("click", event => {
        event.stopPropagation();
        const utterance = new SpeechSynthesisUtterance(word);
        utterance.lang = "en-US";
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
      });
      return;
    }

    let audioContext = null;
    let audioBuffer = null;
    window.VocabCardApi.loadAudio(entry.audioUrl).then(async audioData => {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) throw new Error("Web Audio API is unavailable");
      audioContext = new AudioContext();
      audioBuffer = await audioContext.decodeAudioData(audioData);
      playButton.disabled = false;
      playButton.title = "播放发音";
    }).catch(error => {
      playButton.title = "音频加载失败";
      const status = popup?.querySelector(".vocab-card-status");
      if (status) status.textContent = isInvalidExtensionContext(error)
        ? "插件已更新，请刷新页面"
        : "发音加载失败";
      console.warn("Vocab Card audio loading failed", error);
    });
    playButton.addEventListener("click", event => {
      event.stopPropagation();
      if (!audioContext || !audioBuffer) return;
      audioContext.resume().then(() => {
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start(0);
        const status = popup?.querySelector(".vocab-card-status");
        if (status) status.textContent = "";
      }).catch(error => {
        const status = popup?.querySelector(".vocab-card-status");
        if (status) status.textContent = "发音播放失败";
        console.warn("Vocab Card audio playback failed", error);
      });
    });
  }

  function positionPopup(rect) {
    if (!popup) return;
    const popupRect = popup.getBoundingClientRect();
    const position = calculatePopupPosition({
      selectionRect: rect,
      popupWidth: popupRect.width,
      popupHeight: popupRect.height,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight
    });
    popup.style.left = `${position.left}px`;
    popup.style.top = `${position.top}px`;
  }

  function popupHtml(word, body, titleExtra = "") {
    return `
      <button class="vocab-card-close" type="button" aria-label="Close">×</button>
      <div class="vocab-card-heading">
        <div class="vocab-card-title" lang="en">${escapeHtml(word)}</div>
        ${titleExtra}
      </div>
      ${body}
    `;
  }

  async function collectCurrentWord(event) {
    event?.stopPropagation();
    if (!lastSelection || !popup) return;
    const button = popup.querySelector('[data-action="collect"]');
    if (!button || button.disabled) return;
    const currentPopup = popup;
    setCollectStatus("saving");
    try {
      await window.VocabCardApi.collectWord(lastSelection);
      if (popup !== currentPopup) return;
      if (lastSelection.dictionaryEntry) lastSelection.dictionaryEntry.collected = true;
      setCollectStatus("saved");
    } catch (error) {
      if (popup !== currentPopup) return;
      setCollectStatus("error", collectErrorMessage(error));
    }
  }

  function collectErrorMessage(error) {
    if (isInvalidExtensionContext(error)) return "插件已更新，请刷新页面后重试";
    if (isNetworkError(error)) return "无法连接生词本服务器，请确认后端已启动";
    return "加入失败，请稍后重试";
  }

  function isInvalidExtensionContext(error) {
    const message = String(error?.message || error || "");
    return message.includes("Extension context invalidated");
  }

  function isNetworkError(error) {
    const message = String(error?.message || error || "");
    return error instanceof TypeError
      || message.includes("Failed to fetch")
      || message.includes("NetworkError");
  }

  function lookupErrorMessage(error) {
    if (isInvalidExtensionContext(error)) return "插件已更新，请刷新页面";
    if (isNetworkError(error)) return "网络或词典服务不可用";
    return "查词服务暂时不可用";
  }

  document.addEventListener("click", event => {
    if (event.target.classList && event.target.classList.contains("vocab-card-close")) {
      event.stopPropagation();
      dismissPopup();
      return;
    }
    if (popup && !popup.contains(event.target)) dismissPopup();
  });

  function dismissPopup() {
    lookupRequestId += 1;
    removePopup();
    const selection = window.getSelection();
    if (selection) selection.removeAllRanges();
  }

  function removePopup() {
    if (popup) {
      popup.remove();
      popup = null;
    }
  }

})();
