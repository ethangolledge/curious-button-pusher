const cards = [...document.querySelectorAll(".card[data-id]")];
const overall = document.getElementById("overall");
const submit = document.getElementById("submit");
const count = document.getElementById("count");
const player = document.getElementById("player");
const blocked = document.querySelector(".bar[data-blocked]") !== null;
const review = Number(document.body.dataset.review);
const draftKey = `content:${document.title}:${review}`;

function notes() {
  const lines = cards
    .map((card) => [card, card.querySelector(".note").value.trim()])
    .filter(([, note]) => note)
    .map(([card, note]) => {
      const kind = card.querySelector(".kind");
      return `${card.dataset.id}${kind ? ` [${kind.value}]` : ""}: ${note}`;
    });
  if (overall && overall.value.trim()) lines.push(overall.value.trim());
  return lines;
}

const whole = document.getElementById("whole");

// Lines rewritten in the person's own words, used exactly.
function edits() {
  const changed = {};
  for (const card of cards) {
    const own = card.querySelector(".own");
    if (own && own.value.trim() && own.value.trim() !== own.dataset.original.trim()) {
      changed[card.dataset.id] = own.value.trim();
    }
  }
  return changed;
}

function refresh() {
  if (!submit) return;
  const n = notes().length + Object.keys(edits()).length;
  count.textContent = n ? `${n} change${n > 1 ? "s" : ""}` : "No comments";
  submit.textContent = n ? "Send changes" : "Approve";
  submit.disabled = !n && blocked;
  const label = document.getElementById("whole-label");
  if (label) label.hidden = !notes().length;
  const own = edits();
  for (const card of cards) {
    const noted = card.querySelector(".note").value.trim() !== "";
    card.classList.toggle("noted", noted || card.dataset.id in own);
  }
}

for (const card of cards) {
  const note = card.querySelector(".note");
  const box = card.querySelector(".note-box");
  card.querySelector(".comment").addEventListener("click", () => {
    box.hidden = !box.hidden;
    if (!box.hidden) note.focus();
  });
  const kind = card.querySelector(".kind");
  if (kind) kind.addEventListener("change", changed);
  note.addEventListener("input", changed);
  const own = card.querySelector(".own");
  if (own) {
    card.querySelector(".edit").addEventListener("click", () => {
      own.hidden = !own.hidden;
      if (!own.hidden) own.focus();
    });
    own.addEventListener("input", changed);
  }
  const play = card.querySelector(".play");
  if (play && player) {
    play.addEventListener("click", () => {
      player.currentTime = Number(play.dataset.start);
      player.play();
      player.scrollIntoView({behavior: "smooth", block: "center"});
    });
  }
}
if (overall) overall.addEventListener("input", changed);

// Comments are saved as they are typed: in this browser, and in the run folder when the
// review server is running, so a closed window or a stopped run loses none of them.
function draft() {
  const notes = {};
  const kinds = {};
  for (const card of cards) {
    const note = card.querySelector(".note").value;
    if (note.trim()) notes[card.dataset.id] = note;
    const kind = card.querySelector(".kind");
    if (kind) kinds[card.dataset.id] = kind.value;
  }
  return {notes, kinds, edits: edits(), overall: overall ? overall.value : ""};
}

let saving = null;
function changed() {
  refresh();
  clearTimeout(saving);
  saving = setTimeout(() => {
    const value = draft();
    try { localStorage.setItem(draftKey, JSON.stringify(value)); } catch (e) {}
    if (review) {
      fetch("/draft", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({review, draft: value})}).catch(() => null);
    }
  }, 500);
}

function restore(value) {
  if (!value) return;
  for (const card of cards) {
    const note = card.querySelector(".note");
    const saved = (value.notes || {})[card.dataset.id];
    if (saved && !note.value) {
      note.value = saved;
      card.querySelector(".note-box").hidden = false;
    }
    const kind = card.querySelector(".kind");
    const chosen = (value.kinds || {})[card.dataset.id];
    if (kind && chosen) kind.value = chosen;
    const own = card.querySelector(".own");
    const words = (value.edits || {})[card.dataset.id];
    if (own && words) { own.value = words; own.hidden = false; }
  }
  if (overall && value.overall && !overall.value) overall.value = value.overall;
  refresh();
}

async function load() {
  let value = null;
  if (review) {
    const saved = await fetch(`.work/reviews/draft-${review}.json`).catch(() => null);
    if (saved && saved.ok) value = await saved.json().catch(() => null);
  }
  if (!value) {
    try { value = JSON.parse(localStorage.getItem(draftKey) || "null"); } catch (e) {}
  }
  restore(value);
}

async function send(action) {
  const feedback = notes().join("\n");
  const own = edits();
  const scope = whole && whole.checked ? "script" : null;
  const answer = await fetch("/respond", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({action, feedback, edits: own, scope})}).catch(() => null);
  if (!answer || !answer.ok) {
    const unsent = document.getElementById("unsent");
    unsent.querySelector("textarea").value =
      `${action === "revise" ? "Revise" : action === "stop" ? "Stop" : "Approve"}` +
      (scope ? " (rewrite the whole script)" : "") +
      Object.entries(own).map(([id, words]) => `
${id}, in my words: ${words}`).join("") +
      (feedback ? `
${feedback}` : "");
    unsent.hidden = false;
    return;
  }
  document.getElementById("sent").hidden = false;
  setTimeout(() => window.close(), 1200);
  setTimeout(() => {
    document.querySelector("#sent p").textContent = "Sent. You can close this window.";
  }, 2500);
}

if (submit) {
  submit.addEventListener("click", () =>
    send(notes().length || Object.keys(edits()).length ? "revise" : "approve"));
  document.getElementById("stop").addEventListener("click", () => send("stop"));
  document.getElementById("copy").addEventListener("click", () => {
    const text = document.querySelector("#unsent textarea");
    text.select();
    navigator.clipboard.writeText(text.value).catch(() => document.execCommand("copy"));
  });
  refresh();
  load();
}
