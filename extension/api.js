(function () {
  const DEFAULT_SERVER_URL = "http://127.0.0.1:8001";

  async function getServerConfig() {
    const stored = await chrome.storage.local.get(["serverUrl", "accessToken"]);
    return {
      serverUrl: (stored.serverUrl || DEFAULT_SERVER_URL).replace(/\/$/, ""),
      accessToken: stored.accessToken || ""
    };
  }

  function authHeaders(accessToken, extra = {}) {
    return accessToken ? {...extra, "X-Access-Token": accessToken} : extra;
  }

  async function lookupWord(word, sentence = "") {
    try {
      const {serverUrl, accessToken} = await getServerConfig();
      const params = new URLSearchParams({word});
      if (sentence) params.set("sentence", sentence);
      const response = await fetch(`${serverUrl}/dictionary/lookup?${params.toString()}`, {
        headers: authHeaders(accessToken)
      });
      if (response.ok) return response.json();
      if (response.status !== 404) throw new Error(`Backend dictionary failed: ${response.status}`);
    } catch (error) {
      // Fall back to the public free dictionary so reading is still usable if the backend is down.
    }

    const response = await fetch(`https://api.dictionaryapi.dev/api/v2/entries/en/${encodeURIComponent(word)}`);
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`Dictionary API failed: ${response.status}`);
    const payload = await response.json();
    return parseDictionary(payload);
  }

  function parseDictionary(payload) {
    if (!Array.isArray(payload) || !payload.length) return null;
    const entry = payload[0];
    const meaning = (entry.meanings || [])[0] || {};
    const definitions = (meaning.definitions || [])
      .map(item => item.definition)
      .filter(Boolean)
      .slice(0, 3);
    const phonetics = entry.phonetics || [];
    const phonetic = (phonetics.find(item => item.text) || {}).text || "";
    const audios = phonetics.map(item => item.audio).filter(Boolean);
    const audioUrl = audios.find(url => /-us|us\.mp3/i.test(url)) || audios[0] || "";
    return {
      word: entry.word,
      partOfSpeech: meaning.partOfSpeech || "",
      definitions,
      phonetic,
      audioUrl,
      collected: false
    };
  }

  async function collectWord({word, sentence, sourceUrl, dictionaryEntry}) {
    const {serverUrl, accessToken} = await getServerConfig();
    const response = await fetch(`${serverUrl}/words`, {
      method: "POST",
      headers: authHeaders(accessToken, {"Content-Type": "application/json"}),
      body: JSON.stringify({
        word,
        sentence,
        source_url: sourceUrl,
        definitions: dictionaryEntry?.definitions || [],
        part_of_speech: dictionaryEntry?.partOfSpeech || null,
        phonetic: dictionaryEntry?.phonetic || null,
        audio_url: dictionaryEntry?.audioUrl || null
      })
    });
    if (!response.ok) throw new Error(`Collect failed: ${response.status}`);
    return response.json();
  }

  async function loadAudio(audioUrl) {
    const result = await chrome.runtime.sendMessage({type: "loadAudio", audioUrl});
    if (!result?.ok) throw new Error(result?.error || "Audio request failed");
    const binary = atob(result.base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes.buffer;
  }

  window.VocabCardApi = {lookupWord, collectWord, loadAudio};
})();
