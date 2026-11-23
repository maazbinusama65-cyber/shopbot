// Storefront + chat widget. All dynamic text goes through textContent (no innerHTML).
const API = window.API_BASE;
const $ = (s) => document.querySelector(s);
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  kids.forEach((k) => n.append(k));
  return n;
};
const uid = () => (crypto.randomUUID ? crypto.randomUUID().slice(0, 12) : String(Date.now()));

// Anonymous per-browser identity: user_id persists (long-term memory), thread_id is per conversation.
const store = {
  get(k, mk) { try { let v = localStorage.getItem(k); if (!v) { v = mk(); localStorage.setItem(k, v); } return v; } catch { return mk(); } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
const userId = store.get("shopbot_user", () => "u-" + uid());
let threadId = store.get("shopbot_thread", () => "t-" + uid());

let products = [], category = "all";
async function loadProducts() {
  try {
    products = await (await fetch(`${API}/products`)).json();
  } catch { $("#grid").replaceChildren(el("p", { textContent: "Couldn't load the catalogue. Is the API running?" })); return; }
  renderFilters(); renderGrid();
}
function renderFilters() {
  const cats = ["all", ...new Set(products.map((p) => p.category))];
  $("#filters").replaceChildren(...cats.map((c) => {
    const b = el("button", { className: "chip", textContent: c, type: "button" });
    b.setAttribute("aria-pressed", String(c === category));
    b.onclick = () => { category = c; renderFilters(); renderGrid(); };
    return b;
  }));
}
function renderGrid() {
  const list = products.filter((p) => category === "all" || p.category === category);
  $("#grid").replaceChildren(...list.map((p) => {
    const low = p.stock > 0 && p.stock <= 5;
    const ask = el("button", { className: "btn sm ghost", type: "button", textContent: p.stock ? "Ask Leaf" : "Sold out" });
    ask.disabled = !p.stock;
    ask.onclick = () => openChat(`Tell me about the ${p.name}`);
    return el("article", { className: "card" },
      el("span", { className: "cat", textContent: p.category }),
      el("h3", { textContent: p.name }),
      el("p", { textContent: p.description }),
      el("div", { className: "row" },
        el("div", {}, el("div", { className: "price", textContent: p.price != null ? `$${p.price.toFixed(2)}` : "—" }),
          el("div", { className: "stock" + (low ? " low" : ""), textContent: p.stock === 0 ? "Out of stock" : low ? `Only ${p.stock} left` : `${p.stock} in stock` })),
        ask));
  }));
}

// ---- chat
const msgs = $("#msgs");
function bubble(text, who, tools) {
  const b = el("div", { className: "m " + who, textContent: text });
  if (tools && tools.length) b.append(el("div", { className: "tools", textContent: "⚙ " + tools.map((t) => t.name).join(" → ") }));
  msgs.append(b); msgs.scrollTop = msgs.scrollHeight; return b;
}
function quick(opts) {
  $("#quick").replaceChildren(...opts.map((o) => {
    const b = el("button", { className: "chip", textContent: o, type: "button" });
    b.onclick = () => send(o); return b;
  }));
}
function greet() {
  msgs.replaceChildren();
  bubble("Hi, I'm Leaf. Ask me about products, today's prices, our return and shipping policy, or what changed recently.", "bot");
  quick(["Running shoes under $80?", "What's your return policy?", "What did the shoes cost in September?"]);
}
function openChat(prefill) {
  $("#chat").classList.add("open"); $("#chat-fab").style.display = "none";
  if (!msgs.children.length) greet();
  if (prefill) send(prefill); else $("#input").focus();
}
let busy = false;
async function send(text) {
  text = text.trim(); if (!text || busy) return;
  busy = true; $("#input").value = ""; $("#quick").replaceChildren();
  bubble(text, "me"); const wait = bubble("Leaf is thinking…", "bot typing");
  try {
    const r = await fetch(`${API}/chat`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, thread_id: threadId, message: text }) });
    if (!r.ok) throw new Error(r.status === 429 ? "You're sending messages too fast." : "Server error");
    const d = await r.json(); wait.remove(); bubble(d.reply, "bot", d.tool_calls);
    if (/reply ['"]?confirm/i.test(d.reply) || d.tool_calls.some((t) => t.name === "place_order")) quick(["Confirm", "Cancel"]);
    if (d.tool_calls.some((t) => t.name === "place_order" || (t.result || "").includes("Order"))) loadProducts();
  } catch (e) { wait.remove(); bubble(e.message || "Something went wrong, please try again.", "bot"); }
  busy = false; $("#input").focus();
}
$("#form").onsubmit = (e) => { e.preventDefault(); send($("#input").value); };
$("#chat-fab").onclick = () => openChat();
$("#hero-chat").onclick = () => openChat();
$("#close-chat").onclick = () => { $("#chat").classList.remove("open"); $("#chat-fab").style.display = ""; };
$("#new-thread").onclick = () => { threadId = "t-" + uid(); store.set("shopbot_thread", threadId); greet(); };
loadProducts();
