async function load() {
  const stored = await chrome.storage.local.get(["serverUrl", "accessToken"]);
  document.getElementById("serverUrl").value = stored.serverUrl || "";
  document.getElementById("accessToken").value = stored.accessToken || "";
}

document.getElementById("save").addEventListener("click", async () => {
  const serverUrl = document.getElementById("serverUrl").value.trim().replace(/\/$/, "");
  const accessToken = document.getElementById("accessToken").value.trim();
  await chrome.storage.local.set({serverUrl, accessToken});
  const status = document.getElementById("status");
  status.textContent = "已保存";
  setTimeout(() => { status.textContent = ""; }, 1500);
});

load();
