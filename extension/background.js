importScripts("core.js");

const DEFAULT_SERVER_URL = "http://127.0.0.1:8001";
const AUDIO_TIMEOUT_MS = 6000;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "loadAudio") return false;

  loadAudio(message.audioUrl)
    .then(base64 => sendResponse({ok: true, base64}))
    .catch(error => sendResponse({ok: false, error: error.message}));
  return true;
});

async function loadAudio(audioUrl) {
  const stored = await chrome.storage.local.get(["serverUrl", "accessToken"]);
  const serverUrl = stored.serverUrl || DEFAULT_SERVER_URL;
  // Server /audio/ needs the access token (an <audio>/fetch from the page has
  // no cookie for it); third-party hosts must be known pronunciation sources.
  const plan = self.VocabCardCore.audioFetchPlan(audioUrl, serverUrl, stored.accessToken || "");
  if (!plan) {
    throw new Error("Unsupported audio URL");
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), AUDIO_TIMEOUT_MS);
  let response;
  try {
    response = await fetch(audioUrl, {headers: plan.headers, signal: controller.signal, credentials: "omit"});
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    throw new Error(`Audio request failed: ${response.status}`);
  }
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (/json|text|html/.test(contentType)) {
    throw new Error(`Audio request returned ${contentType}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  let binary = "";
  const chunkSize = 8192;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}
