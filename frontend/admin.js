const API = window.API_BASE;
const $ = (s) => document.querySelector(s);
const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); kids.forEach((k) => n.append(k)); return n; };
let token = ""; try { token = sessionStorage.getItem("shopbot_admin") || ""; } catch {}

async function api(path, opts = {}) {
  const r = await fetch(API + path, { ...opts, headers: { "Content-Type": "application/json", "X-Admin-Token": token, ...(opts.headers || {}) } });
  if (r.status === 401) { logout(); throw new Error("Bad token"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
function logout() { token = ""; try { sessionStorage.removeItem("shopbot_admin"); } catch {} $("#app").hidden = true; $("#login").hidden = false; }
$("#logout").onclick = (e) => { e.preventDefault(); logout(); };
$("#login").onsubmit = async (e) => {
  e.preventDefault(); token = $("#token").value;
  try { await api("/admin/stats"); try { sessionStorage.setItem("shopbot_admin", token); } catch {} start(); }
  catch (err) { $("#login-err").textContent = err.message; }
};

const TABS = { Overview: overview, Products: productsView, Timeline: timelineView, Orders: ordersView, Conversations: convosView };
function start() {
  $("#login").hidden = true; $("#app").hidden = false;
  $("#tabs").replaceChildren(...Object.keys(TABS).map((t) => {
    const b = el("button", { className: "chip", textContent: t, type: "button" });
    b.onclick = () => show(t); return b;
  }));
  show("Overview");
}
async function show(t) {
  [...$("#tabs").children].forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === t)));
  $("#view").replaceChildren(el("p", { textContent: "Loading…" }));
  try { $("#view").replaceChildren(await TABS[t]()); } catch (e) { $("#view").replaceChildren(el("p", { className: "err", textContent: e.message })); }
}
const table = (heads, rows) => el("div", { className: "panel" }, el("table", {},
  el("thead", {}, el("tr", {}, ...heads.map((h) => el("th", { textContent: h })))),
  el("tbody", {}, ...rows)));
const td = (v) => el("td", {}, v instanceof Node ? v : document.createTextNode(String(v ?? "")));

async function overview() {
  const s = await api("/admin/stats");
  const stat = (n, label) => el("div", { className: "stat" }, el("b", { textContent: n }), el("span", { textContent: label }));
  return el("div", { className: "stats" },
    stat(s.turns, "Agent replies"), stat(s.users, "Customers"), stat(s.orders, "Orders"), stat("$" + Number(s.revenue).toFixed(2), "Revenue"),
    stat(`${s.tin} / ${s.tout}`, "Tokens in / out"), stat("$" + s.est_cost_usd, "Est. LLM cost"), stat(Math.round(s.avg_ms) + " ms", "Avg latency"), stat(s.model, "Model"));
}

async function productsView() {
  const ps = await api("/admin/products");
  const rows = ps.map((p) => {
    const price = el("input", { className: "n", type: "number", step: "0.01", value: p.price ?? "" });
    const when = el("input", { type: "date", title: "Effective from (blank = today)" });
    const stock = el("input", { className: "n", type: "number", value: p.stock });
    const save = el("button", { className: "btn sm", textContent: "Save", type: "button" });
    save.onclick = async () => {
      const body = { stock: Number(stock.value) };
      if (Number(price.value) !== p.price) { body.price = Number(price.value); if (when.value) body.effective_from = when.value; }
      await api(`/admin/products/${p.id}`, { method: "PATCH", body: JSON.stringify(body) }); show("Products");
    };
    return el("tr", {}, td(p.id), td(p.name), td(p.category), td(price), td(when), td(stock), td(p.active ? "yes" : "hidden"), td(save));
  });
  const f = { name: el("input", { placeholder: "Name" }), cat: el("input", { placeholder: "category" }), desc: el("input", { placeholder: "Description" }),
    price: el("input", { type: "number", step: "0.01", placeholder: "Price" }), stock: el("input", { type: "number", placeholder: "Stock" }) };
  const add = el("button", { className: "btn sm", textContent: "Add product", type: "button" });
  add.onclick = async () => {
    await api("/admin/products", { method: "POST", body: JSON.stringify({ name: f.name.value, category: f.cat.value || "general", description: f.desc.value, price: Number(f.price.value), stock: Number(f.stock.value || 0) }) });
    show("Products");
  };
  return el("div", {},
    el("p", { textContent: "Changing a price never overwrites history: the old price is closed on the day before the new one takes effect, and Leaf can still answer “what did it cost in September?”." }),
    table(["ID", "Name", "Category", "Price", "Price effective", "Stock", "Active", ""], rows),
    el("div", { className: "panel" }, el("h3", { textContent: "Add product" }), f.name, " ", f.cat, " ", f.desc, " ", f.price, " ", f.stock, " ", add));
}

async function timelineView() {
  const edges = await api("/admin/timeline");
  const rows = edges.map((e) => el("tr", {}, td(`F${e.id}`), td(e.subject), td(e.relation), td(e.object),
    td(el("span", { className: "tl-bar" + (e.valid_to ? "" : " open"), textContent: `${e.valid_from} → ${e.valid_to || "now"}` })), td(e.source)));
  const f = { s: el("input", { placeholder: "policy:returns" }), r: el("input", { placeholder: "window_days" }), o: el("input", { placeholder: "45" }), d: el("input", { type: "date" }) };
  const add = el("button", { className: "btn sm", textContent: "Add fact", type: "button" });
  add.onclick = async () => { await api("/admin/facts", { method: "POST", body: JSON.stringify({ subject: f.s.value, relation: f.r.value, object: f.o.value, valid_from: f.d.value || null }) }); show("Timeline"); };
  return el("div", {}, el("p", { textContent: "Shop memory: every price, policy and promo as a dated edge. Leaf cites these as [F#]." }),
    table(["Ref", "Subject", "Relation", "Value", "Valid", "Source"], rows),
    el("div", { className: "panel" }, el("h3", { textContent: "Add or schedule a fact" }), f.s, " ", f.r, " ", f.o, " ", f.d, " ", add));
}

async function ordersView() {
  const os = await api("/admin/orders");
  return table(["#", "Customer", "Total", "Status", "When", "Items"], os.map((o) =>
    el("tr", {}, td(o.id), td(o.user_id), td("$" + o.total.toFixed(2)), td(o.status), td(o.created_at.slice(0, 16)),
      td(JSON.parse(o.items_json).map((l) => `${l.qty}× ${l.name}`).join(", ")))));
}

async function convosView() {
  const cs = await api("/admin/conversations");
  const detail = el("div");
  const rows = cs.map((c) => {
    const b = el("button", { className: "btn sm ghost", textContent: "Open", type: "button" });
    b.onclick = async () => {
      const m = await api(`/admin/conversations/${encodeURIComponent(c.user_id)}/${encodeURIComponent(c.thread_id)}`);
      detail.replaceChildren(el("div", { className: "panel" }, ...m.map((x) => {
        const tools = JSON.parse(x.tool_calls_json || "[]").map((t) => t.name).join(", ");
        return el("p", {}, el("b", { textContent: x.role + ": " }), document.createTextNode(x.content), tools ? el("small", { textContent: `  [tools: ${tools}]` }) : "");
      })));
    };
    return el("tr", {}, td(c.user_id), td(c.thread_id), td(c.messages), td(`${c.tokens_in}/${c.tokens_out}`), td(c.last_at.slice(0, 16)), td(b));
  });
  return el("div", {}, table(["Customer", "Thread", "Messages", "Tokens in/out", "Last", ""], rows), detail);
}

if (token) api("/admin/stats").then(start).catch(logout); else logout();
