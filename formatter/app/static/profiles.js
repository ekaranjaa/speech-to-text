const $ = (id) => document.getElementById(id);
let editingExisting = false;

async function refresh() {
  const profiles = await (await fetch("/api/profiles")).json();
  const list = $("list");
  list.innerHTML = "";
  for (const p of profiles) {
    const li = document.createElement("li");
    li.textContent = p.name;
    li.addEventListener("click", () => load(p.id));
    list.appendChild(li);
  }
}

async function load(id) {
  const p = await (await fetch("/api/profiles/" + id)).json();
  editingExisting = true;
  $("edit-id").value = p.id;
  $("name").value = p.name;
  $("description").value = p.description || "";
  $("instructions").value = p.instructions;
  $("model").value = p.model || "";
  $("temperature").value = p.temperature ?? "";
  $("editor-title").textContent = "Editing: " + p.name;
  $("status").textContent = "";
}

function blank() {
  editingExisting = false;
  ["edit-id", "name", "description", "instructions", "model", "temperature"].forEach((k) => ($(k).value = ""));
  $("editor-title").textContent = "New profile";
  $("status").textContent = "";
}

function payload() {
  const body = {
    name: $("name").value,
    description: $("description").value,
    instructions: $("instructions").value,
  };
  if ($("model").value.trim()) body.model = $("model").value.trim();
  if ($("temperature").value !== "") body.temperature = parseFloat($("temperature").value);
  return body;
}

$("new").addEventListener("click", blank);

$("save").addEventListener("click", async () => {
  const id = $("edit-id").value;
  const url = editingExisting ? "/api/profiles/" + id : "/api/profiles";
  const method = editingExisting ? "PUT" : "POST";
  const resp = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload()),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    $("status").textContent = "Error: " + (err.detail || resp.statusText);
    return;
  }
  await refresh();
  const saved = await resp.json();
  await load(saved.id);
  $("status").textContent = "Saved.";
});

$("delete").addEventListener("click", async () => {
  const id = $("edit-id").value;
  if (!id) return;
  await fetch("/api/profiles/" + id, { method: "DELETE" });
  blank();
  await refresh();
});

refresh();
