chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "loadAudio") return false;

  loadAudio(message.audioUrl)
    .then(base64 => sendResponse({ok: true, base64}))
    .catch(error => sendResponse({ok: false, error: error.message}));
  return true;
});

async function loadAudio(audioUrl) {
  if (!/^https:\/\//i.test(audioUrl)) {
    throw new Error("Unsupported audio URL");
  }

  const response = await fetch(audioUrl);
  if (!response.ok) {
    throw new Error(`Audio request failed: ${response.status}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  let binary = "";
  const chunkSize = 8192;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}
