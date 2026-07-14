(function () {
  const DEFAULT_SERVER_URL = "http://127.0.0.1:8001";

  async function getServerUrl() {
    const stored = await chrome.storage.sync.get(["serverUrl"]);
    return (stored.serverUrl || DEFAULT_SERVER_URL).replace(/\/$/, "");
  }

  async function lookupWord(word) {
    try {
      const serverUrl = await getServerUrl();
      const response = await fetch(`${serverUrl}/dictionary/lookup?word=${encodeURIComponent(word)}`);
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
      audioUrl
    };
  }

  async function collectWord({word, sentence, sourceUrl}) {
    const serverUrl = await getServerUrl();
    const response = await fetch(`${serverUrl}/words`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({word, sentence, source_url: sourceUrl})
    });
    if (!response.ok) throw new Error(`Collect failed: ${response.status}`);
    return response.json();
  }

  window.VocabCardApi = {lookupWord, collectWord};
})();
