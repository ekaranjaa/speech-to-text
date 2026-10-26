const $ = (id) => document.getElementById(id);

$("file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (file) $("input").value = await file.text();
});

$("run").addEventListener("click", async () => {
  const text = $("input").value;
  const profile_id = $("profile").value;
  if (!text.trim()) { $("status").textContent = "Paste or upload a transcript first."; return; }
  $("output").value = "";
  $("status").textContent = "Formatting…";
  $("run").disabled = true;
  try {
    const resp = await fetch("/api/format", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, profile_id }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      $("status").textContent = "Error: " + (err.detail || resp.statusText);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      $("output").value += decoder.decode(value, { stream: true });
    }
    $("status").textContent = "Done.";
  } catch (e) {
    $("status").textContent = "Error: " + e.message;
  } finally {
    $("run").disabled = false;
  }
});

$("copy").addEventListener("click", () => navigator.clipboard.writeText($("output").value));

$("download").addEventListener("click", () => {
  const blob = new Blob([$("output").value], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "formatted-transcript.txt";
  a.click();
  URL.revokeObjectURL(a.href);
});
