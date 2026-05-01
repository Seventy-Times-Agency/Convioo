const $ = (id) => document.getElementById(id);

chrome.storage.local.get(["apiUrl", "userId"], (data) => {
  $("apiUrl").value = data.apiUrl || "";
  $("userId").value = data.userId || "";
});

$("save").addEventListener("click", () => {
  const apiUrl = $("apiUrl").value.trim().replace(/\/$/, "");
  const userId = parseInt($("userId").value, 10);
  if (!apiUrl || !Number.isFinite(userId)) {
    $("status").textContent = "Both fields are required.";
    $("status").style.color = "#dc2626";
    return;
  }
  chrome.storage.local.set({ apiUrl, userId }, () => {
    $("status").textContent = "Saved ✓";
    $("status").style.color = "#16a34a";
  });
});
