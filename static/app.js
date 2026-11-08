/* MiniTaxi Almaty frontend: passenger, driver and admin screens */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const money = n => (Number(n) || 0).toLocaleString("en-US") + " ₸";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LABEL_TXT = { requested: "on the way", completed: "completed", cancelled: "cancelled", paid: "paid", failed: "failed", cash: "cash", card: "card" };
const fmtMonth = m => new Date(m + "-01T00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" });

/* =========================== AUTH (token per browser tab) =========================== */
let memToken = null;
const store = {
  get() { try { return sessionStorage.getItem("mt_token") || memToken; } catch { return memToken; } },
  set(t) { memToken = t; try { t ? sessionStorage.setItem("mt_token", t) : sessionStorage.removeItem("mt_token"); } catch {} },
};

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  const t = store.get();
  if (t) headers.Authorization = "Bearer " + t;
  const res = await fetch(path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && state.me) { logout(true); }
  if (!res.ok) throw new Error(data.error || "Server error");
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = "toast"), 3200);
}

function plate(p) {
  const m = String(p || "").match(/^(.*)\s(\d{2})$/);
  const num = m ? m[1] : p, reg = m ? m[2] : "";
  return `<span class="plate"><span class="kz">KZ</span><span class="num">${esc(num)}</span>${reg ? `<span class="reg">${reg}</span>` : ""}</span>`;
}
const badge = s => s ? `<span class="badge ${s}">${LABEL_TXT[s] || esc(s)}</span>` : "";

const state = { me: null, places: [], pickup: "", dropoff: "", table: "passengers", rideFilter: "", view: null };

/* =========================== ROLES & NAVIGATION =========================== */
const ROLE_VIEWS = {
  passenger: [["book", "Book"], ["myrides", "My rides"]],
  driver: [["orders", "My orders"], ["earnings", "Earnings"]],
  admin: [["dispatch", "Dispatch"], ["db", "Database"], ["reports", "Reports"], ["access", "Access & roles"]],
};
const ROLE_NAME = { passenger: "Passenger", driver: "Driver", admin: "Admin" };
const LOADERS = {
  login: loadLogin, book: loadBook, myrides: loadMyRides, orders: loadOrders, earnings: loadEarnings,
  dispatch: loadDispatch, db: loadTable, reports: loadReports, access: renderAccess,
};

function renderShell() {
  const me = state.me;
  const views = me ? ROLE_VIEWS[me.role] : [];
  $("#tabs").innerHTML = views.map(([v, label]) => `<button data-view="${v}">${label}${v === "myrides" || v === "orders" || v === "dispatch" ? ' <span class="pill" data-count hidden></span>' : ""}</button>`).join("");
  $("#brandRole").textContent = me ? "Almaty · " + ROLE_NAME[me.role] : "Almaty";
  const chip = $("#userChip");
  chip.hidden = !me;
  if (me) chip.innerHTML = `<span class="avatar ${me.role}">${esc(me.name.slice(0, 1))}</span><span class="who"><b>${esc(me.name)}</b><small>${ROLE_NAME[me.role]}</small></span><button class="btn ghost small" id="logoutBtn">Log out</button>`;
  $("#resetBtn").hidden = !(me && me.role === "admin");
  document.body.dataset.role = me ? me.role : "guest";
}

function show(view) {
  const allowed = state.me ? ROLE_VIEWS[state.me.role].map(v => v[0]) : ["login"];
  if (!allowed.includes(view)) view = allowed[0];
  state.view = view;
  $$("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + view));
  if (location.hash !== "#" + view) history.replaceState(null, "", "#" + view);
  LOADERS[view]?.().catch(err => toast(err.message, true));
}
$("#tabs").addEventListener("click", e => { const b = e.target.closest("button"); if (b) show(b.dataset.view); });
$("#userChip").addEventListener("click", e => { if (e.target.id === "logoutBtn") logout(); });

async function refreshMe() {
  state.me = await api("/api/me");
}

async function loginWith(payload) {
  const r = await api("/api/login", { method: "POST", body: payload });
  await afterLogin(r.token);
}
async function afterLogin(token) {
  store.set(token);
  await refreshMe();
  renderShell();
  toast("Logged in as " + state.me.name);
  show(ROLE_VIEWS[state.me.role][0][0]);
}
function logout(expired = false) {
  store.set(null);
  state.me = null;
  renderShell();
  show("login");
  if (expired) toast("Session expired, please log in again", true);
}

/* polling: keeps rides live between the passenger and driver tabs */
setInterval(() => {
  if (document.hidden || !state.me) return;
  if (["myrides", "orders", "dispatch"].includes(state.view)) LOADERS[state.view]().catch(() => {});
  if (state.view === "book") renderActiveBanner().catch(() => {});
}, 5000);

/* =========================== LOGIN =========================== */
async function loadLogin() {
  const d = await api("/api/demo-accounts");
  const chips = list => `<span class="demo-label">Demo accounts:</span>` + list.map(a => `<button type="button" class="chip" data-phone="${esc(a.phone)}">${esc(a.full_name.split(" ")[0])}</button>`).join("");
  $('[data-demo="passengers"]').innerHTML = chips(d.passengers);
  $('[data-demo="drivers"]').innerHTML = chips(d.drivers);
  $("#adminHint").innerHTML = d.admin_hint ? `<span class="demo-label">Demo password:</span> <button type="button" class="chip" data-pass="${esc(d.admin_hint)}">${esc(d.admin_hint)}</button>` : "";
}
$$(".role-card").forEach(form => {
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(form));
    try { await loginWith({ role: form.dataset.role, ...fd }); form.reset(); } catch (err) { toast(err.message, true); }
  });
  form.addEventListener("click", e => {
    const c = e.target.closest(".chip");
    if (!c) return;
    if (c.dataset.phone) form.phone.value = c.dataset.phone;
    if (c.dataset.pass) form.password.value = c.dataset.pass;
    form.requestSubmit();
  });
});
$("#signupBtn").addEventListener("click", () => openModal(`
  <h2>Create an account</h2><p class="muted">Adds a row to PASSENGERS.</p>
  ${passengerFields()}
  <div class="actions"><button class="btn ghost" value="cancel" formnovalidate>Cancel</button><button class="btn primary">Sign up</button></div>`,
  async fd => { const r = await api("/api/signup", { method: "POST", body: Object.fromEntries(fd) }); await afterLogin(r.token); }));

function passengerFields() {
  return `<label class="field"><span>full_name</span><input type="text" name="full_name" placeholder="e.g. Aidana Serikova" required></label>
    <label class="field"><span>phone</span><input type="tel" name="phone" placeholder="+7 701 123 45 67" required></label>
    <label class="field"><span>email</span><input type="email" name="email" placeholder="name@mail.kz"></label>`;
}

function openModal(html, onSubmit) {
  const dlg = $("#modal"), form = $("#modalForm");
  form.innerHTML = html;
  form.onsubmit = async e => {
    if (e.submitter?.value === "cancel") return;
    e.preventDefault();
    try { await onSubmit(new FormData(form)); dlg.close(); } catch (err) { toast(err.message, true); }
  };
  dlg.showModal();
}

/* =========================== MAP =========================== */
const BBOX = { minLng: 76.80, maxLng: 77.11, minLat: 43.10, maxLat: 43.375 };
const W = 800, H = 560;
const px = lng => ((lng - BBOX.minLng) / (BBOX.maxLng - BBOX.minLng)) * W;
const py = lat => ((BBOX.maxLat - lat) / (BBOX.maxLat - BBOX.minLat)) * H;
// label offsets [dx, dy, anchor] so labels don't overlap in the centre
const LABEL = {
  bazaar: [12, -6, "start"], panfilov: [12, 12, "start"], arbat: [-11, -8, "end"], kbtu: [-11, 8, "end"],
  almaty2: [-11, -4, "end"], republic: [0, -11, "middle"], dostyk: [10, 15, "start"], koktobe: [12, 2, "start"],
  satbayev: [-11, -6, "end"], stadium: [-11, 10, "end"], kaznu: [-11, 2, "end"], esentai: [11, 6, "start"],
  botanic: [-11, 12, "end"], mega: [-11, 10, "end"], sairan: [0, -14, "middle"], arena: [0, 22, "middle"],
  medeu: [12, 4, "start"], shymbulak: [12, 4, "start"], airport: [-12, 4, "end"], almaty1: [12, 4, "start"],
};
const STREETS = [
  { name: "Raiymbek Ave", lat: 43.2665, h: true },
  { name: "Abay Ave", lat: 43.2405, h: true },
  { name: "Al-Farabi Ave", lat: 43.2195, h: true },
  { name: "Dostyk Ave", lng: 76.9585, v: true, from: 43.215, to: 43.31 },
  { name: "Sain St", lng: 76.857, v: true, from: 43.2, to: 43.3 },
  { name: "Seifullin Ave", lng: 76.9375, v: true, from: 43.215, to: 43.34 },
];

function drawMap() {
  let g = `<defs><pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse" patternTransform="rotate(-4)">
          <path d="M26 0H0V26" fill="none" stroke="#dfe5ef" stroke-width="1"/></pattern>
        <linearGradient id="mtn" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5d7fa8"/><stop offset="1" stop-color="#2f527a"/></linearGradient></defs>
        <rect width="${W}" height="${H}" fill="url(#grid)"/>`;
  const ridge = [[0, 470], [60, 440], [110, 455], [170, 420], [230, 445], [300, 405], [360, 430], [420, 390], [470, 412], [530, 372], [590, 400], [650, 360], [700, 380], [760, 345], [800, 360], [800, 560], [0, 560]];
  g += `<path d="M${ridge.map(p => p.join(" ")).join(" L")}Z" fill="url(#mtn)" opacity=".9"/>`;
  g += `<path d="M300 405 L312 420 L292 418Z M420 390 L433 404 L410 403Z M530 372 L545 388 L519 386Z M650 360 L664 374 L638 373Z M760 345 L774 358 L748 358Z" fill="#fff"/>`;
  g += `<text x="${W - 16}" y="${H - 16}" text-anchor="end" font-family="Manrope" font-size="12" font-weight="700" fill="#fff" opacity=".8" letter-spacing="2">ILE ALATAU</text>`;
  g += `<path d="M${px(76.935)} ${py(43.18)} C ${px(76.93)} ${py(43.23)}, ${px(76.945)} ${py(43.27)}, ${px(76.94)} ${py(43.36)}" fill="none" stroke="#b9d3ee" stroke-width="3"/>`;
  for (const s of STREETS) {
    if (s.h) {
      const y = py(s.lat);
      g += `<line x1="0" y1="${y}" x2="${W}" y2="${y + 18}" stroke="#fff" stroke-width="6"/><line x1="0" y1="${y}" x2="${W}" y2="${y + 18}" stroke="#cdd7e6" stroke-width="1"/>
            <text x="8" y="${y - 5}" font-size="10.5" fill="#8a96ad" font-family="Manrope" font-weight="600">${s.name}</text>`;
    } else {
      const x = px(s.lng);
      g += `<line x1="${x}" y1="${py(s.to)}" x2="${x + 6}" y2="${py(s.from)}" stroke="#fff" stroke-width="6"/><line x1="${x}" y1="${py(s.to)}" x2="${x + 6}" y2="${py(s.from)}" stroke="#cdd7e6" stroke-width="1"/>
            <text transform="translate(${x - 4} ${py(s.to) + 6}) rotate(90)" font-size="10.5" fill="#8a96ad" font-family="Manrope" font-weight="600">${s.name}</text>`;
    }
  }
  const a = state.places.find(p => p.name === state.pickup), b = state.places.find(p => p.name === state.dropoff);
  if (a && b) {
    const x1 = px(a.lng), y1 = py(a.lat), x2 = px(b.lng), y2 = py(b.lat);
    const mx = (x1 + x2) / 2 + (y2 - y1) * 0.18, my = (y1 + y2) / 2 - (x2 - x1) * 0.18;
    g += `<path class="route-path" d="M${x1} ${y1} Q${mx} ${my} ${x2} ${y2}"/>`;
  }
  for (const p of state.places) {
    const [dx, dy, anchor] = LABEL[p.id] || [12, 4, "start"];
    const cls = p.name === state.pickup ? "a" : p.name === state.dropoff ? "b" : "";
    const inMountains = p.id === "medeu" || p.id === "shymbulak";
    g += `<g class="pt ${cls}" data-name="${esc(p.name)}" transform="translate(${px(p.lng)} ${py(p.lat)})">
            <circle r="16" fill="transparent"/><circle class="core" r="6.5"/>
            <text x="${dx}" y="${dy}" text-anchor="${anchor}" ${inMountains ? 'style="fill:#fff;stroke:#2f527a"' : ""}>${esc(p.name)}</text>
          </g>`;
  }
  $("#map").innerHTML = g;
}
$("#map").addEventListener("click", e => {
  const pt = e.target.closest(".pt");
  if (!pt) return;
  const name = pt.dataset.name;
  if (!state.pickup || (state.pickup && state.dropoff)) { state.pickup = name; state.dropoff = ""; }
  else if (name !== state.pickup) state.dropoff = name;
  syncRoute();
});

/* =========================== PASSENGER: BOOK =========================== */
function placeOptions(placeholder) {
  const byDistrict = {};
  for (const p of state.places) (byDistrict[p.district] ||= []).push(p);
  return `<option value="">${placeholder}</option>` + Object.entries(byDistrict).map(([d, ps]) =>
    `<optgroup label="${d} District">${ps.map(p => `<option>${esc(p.name)}</option>`).join("")}</optgroup>`).join("");
}

async function loadBook() {
  if (!state.places.length) {
    state.places = await api("/api/places");
    $("#pickupSelect").innerHTML = placeOptions("Pickup point");
    $("#dropoffSelect").innerHTML = placeOptions("Where to?");
  }
  $("#greeting").textContent = `Where to, ${state.me.name.split(" ")[0]}?`;
  syncRoute();
  await renderActiveBanner();
}

let hadActive = null;
async function renderActiveBanner() {
  const rides = await api("/api/my/rides");
  const active = rides.find(r => r.status === "requested");
  setCount(active ? 1 : 0);
  // ride just finished while we were watching
  if (hadActive && !active) {
    const done = rides.find(r => r.ride_id === hadActive);
    if (done) toast(done.status === "completed" ? `Ride #${done.ride_id} completed, payment ${LABEL_TXT[done.last_payment_status] || ""}` : `Ride #${done.ride_id} ${LABEL_TXT[done.status]}`, done.last_payment_status === "failed");
  }
  hadActive = active ? active.ride_id : null;
  $("#activeBanner").innerHTML = active ? rideBanner(active) : "";
  $("#orderBtn").dataset.blocked = active ? "1" : "";
  updateOrderBtn();
}

function rideBanner(r) {
  const eta = 3 + (r.ride_id % 6);
  return `<div class="card confirm">
      <div><div class="ride-id">ride #${r.ride_id} · ${esc(r.start_time)} · <span class="live"><i></i>driver on the way</span></div>
        <h3>${esc(r.driver_name)} <span class="stars">★ ${Number(r.driver_rating).toFixed(1)}</span> <span class="muted" style="font-size:13px;font-weight:500">${esc(r.driver_phone || "")}</span></h3>
        <div style="margin-top:6px">${esc(r.car_model)}, ${esc(r.car_color || "")} &nbsp;${plate(r.plate_number)}</div>
        <div class="muted" style="margin-top:6px">${esc(r.pickup_address)} → ${esc(r.dropoff_address)} · <b>${money(r.price)}</b></div></div>
      <div class="eta">arrives in ~${eta} min<br><button class="btn danger small" data-act="cancel" data-id="${r.ride_id}">Cancel ride</button></div></div>`;
}

async function syncRoute() {
  $("#pickupSelect").value = state.pickup;
  $("#dropoffSelect").value = state.dropoff;
  $("#mapTip").textContent = !state.pickup ? "Click the pickup point, then the drop-off point"
    : !state.dropoff ? "Now choose where to go" : `${state.pickup} → ${state.dropoff}`;
  drawMap();
  const box = $("#quoteBox");
  state.quoteOk = false;
  if (!state.pickup || !state.dropoff) {
    box.innerHTML = `<div class="quote-empty">Choose a route to see the price</div>`;
    return updateOrderBtn();
  }
  try {
    const q = await api("/api/quote", { method: "POST", body: { pickup: state.pickup, dropoff: state.dropoff } });
    box.innerHTML = `<div class="quote-body">
      <div><div class="quote-meta">${q.distance_km} km · ~${q.minutes} min ride</div>
        ${q.night ? '<span class="tag night">night fare ×1.2</span>' : ""}${q.mountain ? '<span class="tag mountain">mountains +600 ₸</span>' : ""}</div>
      <div class="quote-price">${money(q.price)}</div></div>`;
    state.quoteOk = true;
  } catch (err) {
    box.innerHTML = `<div class="quote-empty">${esc(err.message)}</div>`;
  }
  updateOrderBtn();
}
function updateOrderBtn() {
  const btn = $("#orderBtn"), blocked = btn.dataset.blocked === "1";
  btn.disabled = blocked || !state.quoteOk;
  btn.textContent = blocked ? "You already have a ride" : "Book a taxi";
}

$("#pickupSelect").addEventListener("change", e => { state.pickup = e.target.value; syncRoute(); });
$("#dropoffSelect").addEventListener("change", e => { state.dropoff = e.target.value; syncRoute(); });
$("#swapBtn").addEventListener("click", () => { [state.pickup, state.dropoff] = [state.dropoff, state.pickup]; syncRoute(); });

$("#orderForm").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = $("#orderBtn");
  btn.disabled = true; btn.textContent = "Finding a driver…";
  try {
    const r = await api("/api/rides", { method: "POST", body: { pickup: state.pickup, dropoff: state.dropoff } });
    toast(`Ride #${r.ride_id} booked`);
    state.pickup = state.dropoff = "";
    await syncRoute();
    await renderActiveBanner();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) { toast(err.message, true); updateOrderBtn(); }
});

/* =========================== PASSENGER: MY RIDES =========================== */
async function loadMyRides() {
  const [rides] = await Promise.all([api("/api/my/rides"), refreshMe()]);
  const s = state.me.stats;
  const active = rides.find(r => r.status === "requested");
  setCount(active ? 1 : 0);
  $("#pStats").innerHTML = `
    <div class="stat"><b>${s.rides}</b><span>trips with MiniTaxi</span></div>
    <div class="stat"><b>${money(s.spent)}</b><span>spent on completed trips</span></div>
    <div class="stat accent"><b>${esc(state.me.profile.registration_date)}</b><span>member since</span></div>`;
  const unpaid = rides.filter(r => r.status === "completed" && r.last_payment_status === "failed");
  $("#pActive").innerHTML = (active ? rideBanner(active) : "") + unpaid.map(r => `
    <div class="card alert"><b>Payment for ride #${r.ride_id} failed.</b> ${esc(r.pickup_address)} → ${esc(r.dropoff_address)} · ${money(r.price)}
      <button class="btn primary small" data-act="pay" data-id="${r.ride_id}">Pay again by card</button></div>`).join("");
  $("#pHistory").innerHTML = `<thead><tr><th>#</th><th>Time</th><th>Route</th><th>Driver</th><th>Car</th><th>Price</th><th>Status</th><th>Payment</th></tr></thead><tbody>${
    rides.map(r => `<tr><td>${r.ride_id}</td><td>${esc(r.start_time)}</td><td class="wrap">${esc(r.pickup_address)} → ${esc(r.dropoff_address)}</td>
      <td>${esc(r.driver_name)}</td><td>${esc(r.car_model)}</td><td><b>${money(r.price)}</b></td><td>${badge(r.status)}</td>
      <td>${r.last_payment_status ? badge(r.last_payment_status) + ` <span class="muted">${LABEL_TXT[r.last_payment_method]}</span>` : "—"}</td></tr>`).join("")
    || '<tr><td colspan="8" class="muted">No trips yet</td></tr>'}</tbody>`;
}

/* =========================== DRIVER: ORDERS =========================== */
async function loadOrders() {
  const [rides] = await Promise.all([api("/api/driver/rides"), refreshMe()]);
  const p = state.me.profile, cars = state.me.cars;
  const active = rides.find(r => r.status === "requested");
  setCount(active ? 1 : 0);
  $("#dHead").innerHTML = `
    <div><div class="muted" style="font-size:13px">driver #${p.driver_id} · license ${esc(p.license_number)}</div>
      <h2>${esc(p.full_name)} <span class="stars">★ ${Number(p.rating).toFixed(1)}</span></h2></div>
    <div class="cars">${cars.map(c => `<div class="car">${plate(c.plate_number)}<span>${esc(c.model)} · ${esc(c.color || "")}</span></div>`).join("")}</div>
    <div class="status ${active ? "busy" : "free"}"><i></i>${active ? "On a ride" : "Online · waiting"}</div>`;
  $("#dActive").innerHTML = active ? `
    <div class="card order-now">
      <div class="order-top"><span class="ride-id">ride #${active.ride_id} · ${esc(active.start_time)}</span><span class="ride-price">${money(active.price)}</span></div>
      <div class="ride-route big"><i class="dot a"></i><span>${esc(active.pickup_address)}</span><i class="dot b"></i><span>${esc(active.dropoff_address)}</span></div>
      <div class="ride-who"><span>Passenger: <b>${esc(active.passenger_name)}</b> · ${esc(active.passenger_phone || "")}</span><span>Car: ${plate(active.plate_number)}</span></div>
      <div class="ride-actions">
        <button class="btn blue" data-act="complete" data-id="${active.ride_id}" data-m="cash">Complete · cash</button>
        <button class="btn blue" data-act="complete" data-id="${active.ride_id}" data-m="card">Complete · card</button>
        <button class="btn ghost" data-act="fail" data-id="${active.ride_id}" title="Simulate a declined card">Card declined</button>
      </div></div>`
    : `<div class="empty waiting"><span class="pulse"></span><b>No order yet</b><br>Rides go to the free driver with the highest rating.</div>`;
  const unpaid = rides.filter(r => r.status === "completed" && r.last_payment_status === "failed");
  $("#dUnpaid").innerHTML = unpaid.map(r => `
    <div class="card alert"><b>Ride #${r.ride_id}: card declined.</b> ${esc(r.passenger_name)} · ${money(r.price)}
      <button class="btn primary small" data-act="pay" data-id="${r.ride_id}">Got cash</button></div>`).join("");
  const done = rides.filter(r => r.status !== "requested");
  $("#dHistory").innerHTML = `<thead><tr><th>#</th><th>Time</th><th>Passenger</th><th>Route</th><th>Car</th><th>Price</th><th>Status</th><th>Payment</th></tr></thead><tbody>${
    done.map(r => `<tr><td>${r.ride_id}</td><td>${esc(r.start_time)}</td><td>${esc(r.passenger_name)}</td><td class="wrap">${esc(r.pickup_address)} → ${esc(r.dropoff_address)}</td>
      <td>${plate(r.plate_number)}</td><td><b>${money(r.price)}</b></td><td>${badge(r.status)}</td><td>${badge(r.last_payment_status) || "—"}</td></tr>`).join("")
    || '<tr><td colspan="8" class="muted">No rides yet</td></tr>'}</tbody>`;
}

/* =========================== DRIVER: EARNINGS =========================== */
async function loadEarnings() {
  const e = await api("/api/driver/earnings");
  const cur = e.monthly.find(m => m.month === e.month) || { rides: 0, earnings_kzt: 0 };
  const max = Math.max(1, ...e.monthly.map(m => m.earnings_kzt));
  $("#dEarn").innerHTML = `
    <div class="stats three">
      <div class="stat accent"><b>${money(cur.earnings_kzt)}</b><span>earned in ${fmtMonth(e.month)}</span></div>
      <div class="stat"><b>${cur.rides}</b><span>paid rides this month</span></div>
      <div class="stat"><b>${e.place ? `#${e.place} of ${e.total_drivers}` : "—"}</b><span>${e.place === 1 ? "first place, you get the bonus" : "your place this month (first place gets a bonus)"}</span></div>
    </div>
    <div class="card" style="padding:20px;margin-top:16px"><h3>By month</h3><div class="bars">${
      e.monthly.map((m, i) => `<div class="bar-row ${i === 0 ? "top" : ""}"><div class="name">${fmtMonth(m.month)}<small>${m.rides} rides</small></div>
        <div class="bar-track"><div class="bar-fill" style="width:0" data-w="${(m.earnings_kzt / max) * 100}%"></div></div><div class="val">${money(m.earnings_kzt)}</div></div>`).join("")
      || '<p class="muted">No paid rides yet</p>'}</div></div>`;
  requestAnimationFrame(() => $$("#dEarn .bar-fill").forEach(el => (el.style.width = el.dataset.w)));
}

/* =========================== ADMIN: DISPATCH =========================== */
async function loadDispatch() {
  const [s, active, hist] = await Promise.all([
    api("/api/stats"),
    api("/api/rides?status=requested"),
    api("/api/rides?limit=150" + (state.rideFilter ? "&status=" + state.rideFilter : "")),
  ]);
  setCount(s.active_rides);
  $("#stats").innerHTML = `
    <div class="stat"><b>${s.free_drivers} / ${s.drivers}</b><span>drivers available</span></div>
    <div class="stat"><b>${s.active_rides}</b><span>rides on the way now</span></div>
    <div class="stat"><b>${s.rides}</b><span>rides total · ${s.passengers} passengers</span></div>
    <div class="stat accent"><b>${money(s.month_revenue)}</b><span>revenue this month</span></div>`;
  $("#activeRides").innerHTML = active.length ? active.map(r => `
    <div class="card ride-card">
      <div class="ride-top"><div><div class="ride-id">ride #${r.ride_id} · ${esc(r.start_time)}</div>${badge("requested")}</div>
        <div class="ride-price">${money(r.price)}</div></div>
      <div class="ride-route"><i class="dot a"></i><span>${esc(r.pickup_address)}</span><i class="dot b"></i><span>${esc(r.dropoff_address)}</span></div>
      <div class="ride-who"><span>Passenger: ${esc(r.passenger_name)}</span><span>Driver: ${esc(r.driver_name)} · ${plate(r.plate_number)}</span></div>
      <div class="ride-actions"><button class="btn danger small" data-act="cancel" data-id="${r.ride_id}">Cancel ride</button></div></div>`).join("")
    : `<div class="empty">No rides on the way right now.</div>`;
  const list = hist.filter(r => r.status !== "requested" || state.rideFilter);
  $("#historyTable").innerHTML = `<thead><tr><th>#</th><th>Time</th><th>Passenger</th><th>Driver</th><th>Route</th><th>Price</th><th>Status</th><th>Payment</th></tr></thead><tbody>${
    list.map(r => `<tr><td>${r.ride_id}</td><td>${esc(r.start_time)}</td><td>${esc(r.passenger_name)}</td><td>${esc(r.driver_name)}</td>
      <td class="wrap">${esc(r.pickup_address)} → ${esc(r.dropoff_address)}</td><td><b>${money(r.price)}</b></td><td>${badge(r.status)}</td>
      <td>${r.last_payment_status ? badge(r.last_payment_status) + ` <span class="muted">${LABEL_TXT[r.last_payment_method]}</span>` : "—"}</td></tr>`).join("")}</tbody>`;
}
$("#rideFilter").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  $$("#rideFilter button").forEach(x => x.classList.toggle("active", x === b));
  state.rideFilter = b.dataset.s;
  loadDispatch();
});

function setCount(n) {
  const pill = $("#tabs [data-count]");
  if (!pill) return;
  pill.textContent = n;
  pill.hidden = !n;
}

/* ride actions for all roles (the server checks who is allowed) */
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const id = b.dataset.id;
  b.disabled = true;
  try {
    if (b.dataset.act === "complete") {
      await api(`/api/rides/${id}/complete`, { method: "POST", body: { method: b.dataset.m } });
      toast(`Ride #${id} completed, payment saved`);
    } else if (b.dataset.act === "fail") {
      await api(`/api/rides/${id}/complete`, { method: "POST", body: { method: "card", simulate_fail: true } });
      toast(`Card declined, saved in PAYMENTS as failed`, true);
    } else if (b.dataset.act === "cancel") {
      await api(`/api/rides/${id}/cancel`, { method: "POST" });
      if (state.view === "book") hadActive = null;
      toast(`Ride #${id} cancelled`);
    } else if (b.dataset.act === "pay") {
      const r = await api(`/api/rides/${id}/pay`, { method: "POST" });
      toast(`Ride #${id} paid by ${r.method}`);
    }
    LOADERS[state.view]?.();
  } catch (err) { toast(err.message, true); b.disabled = false; }
});

/* =========================== ADMIN: DATABASE =========================== */
const TABLES = {
  passengers: { desc: "People who order rides", cols: ["passenger_id", "full_name", "phone", "email", "registration_date", "password_hash"], pk: "passenger_id", fk: {}, why: "Passenger details are stored once, not in every ride." },
  drivers: { desc: "People who drive the cars", cols: ["driver_id", "full_name", "phone", "license_number", "rating", "password_hash"], pk: "driver_id", fk: {}, why: "Driver details and rating are stored once." },
  cars: { desc: "Cars used for rides", cols: ["car_id", "driver_id", "plate_number", "model", "color"], pk: "car_id", fk: { driver_id: "DRIVERS" }, why: "A driver can change cars or have two, so car data is kept separately from the driver (see driver 3)." },
  rides: { desc: "One row for every ride", cols: ["ride_id", "passenger_id", "driver_id", "car_id", "pickup_address", "dropoff_address", "start_time", "status", "price", "ride_rating"], pk: "ride_id", fk: { passenger_id: "PASSENGERS", driver_id: "DRIVERS", car_id: "CARS" }, why: "This is the main action. It connects a passenger, a driver and a car." },
  payments: { desc: "Payment for each ride", cols: ["payment_id", "ride_id", "amount", "method", "payment_status", "paid_at"], pk: "payment_id", fk: { ride_id: "RIDES" }, why: "Payment can fail or happen later, so it has its own record." },
};

function renderErd() {
  $("#erd").innerHTML = Object.entries(TABLES).map(([t, m]) => `
    <div class="erd-box ${t === state.table ? "active" : ""}" data-t="${t}">
      <h4>${t.toUpperCase()} <em>${m.cols.length} fields</em></h4>
      <p>${m.desc}${Object.keys(m.fk).length ? `<br><b style="color:var(--orange)">→ ${Object.values(m.fk).join(", ")}</b>` : ""}</p></div>`).join("");
}
$("#erd").addEventListener("click", e => { const b = e.target.closest(".erd-box"); if (b) { state.table = b.dataset.t; loadTable(); } });
$("#tableTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (b) { state.table = b.dataset.t; loadTable(); } });

async function loadTable(flashId) {
  const t = state.table, m = TABLES[t];
  $$("#tableTabs button").forEach(b => b.classList.toggle("active", b.dataset.t === t));
  renderErd();
  const data = await api("/api/" + t + (t === "rides" ? "?limit=300" : ""));
  const head = m.cols.map(c => `<th>${c}${c === m.pk ? '<span class="k pk">PK</span>' : ""}${m.fk[c] ? '<span class="k fk">FK</span>' : ""}</th>`).join("");
  const body = data.map(r => `<tr${String(r[m.pk]) === String(flashId) ? ' class="flash"' : ""}>${m.cols.map(c => {
    const v = r[c];
    if (["status", "payment_status", "method"].includes(c)) return `<td><span class="badge ${v}">${esc(v)}</span></td>`;
        if (c === "password_hash") return `<td>${v ? "hashed" : '<span class="muted">NULL</span>'}</td>`;
    if (c === "rating") return `<td><span class="stars">★</span> ${Number(v).toFixed(1)}</td>`;
    if (c === "price" || c === "amount") return `<td>${Number(v).toLocaleString("en-US")}</td>`;
    return `<td>${v == null ? '<span class="muted">NULL</span>' : esc(v)}</td>`;
  }).join("")}</tr>`).join("");
  $("#dbTable").innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
  await renderSide(t, data.length);
}

async function renderSide(t, count) {
  const m = TABLES[t];
  let form = "";
  if (t === "passengers") form = passengerFields();
  if (t === "drivers") form = `
    <label class="field"><span>full_name</span><input type="text" name="full_name" required></label>
    <label class="field"><span>phone</span><input type="tel" name="phone" placeholder="+7 7XX XXX XX XX" required></label>
    <label class="field"><span>license_number</span><input type="text" name="license_number" placeholder="AA 1234567" required></label>
    <label class="field"><span>rating (1–5)</span><input type="number" name="rating" min="1" max="5" step="0.1" value="5"></label>`;
  if (t === "cars") {
    const drivers = await api("/api/drivers");
    form = `<label class="field"><span>driver_id → DRIVERS</span><select name="driver_id">${drivers.map(d => `<option value="${d.driver_id}">${d.driver_id} · ${esc(d.full_name)}</option>`).join("")}</select></label>
      <label class="field"><span>plate_number</span><input type="text" name="plate_number" placeholder="123 ABC 02" required></label>
      <label class="field"><span>model</span><input type="text" name="model" placeholder="Chevrolet Cobalt" required></label>
      <label class="field"><span>color</span><input type="text" name="color" placeholder="white"></label>`;
  }
  const fks = Object.entries(m.fk);
  $("#dbSide").innerHTML = `
    <h3 style="font-family:var(--mono)">${t.toUpperCase()}</h3>
    <div class="muted">${count} records · PK: <b>${m.pk}</b></div>
    <div class="why">${m.why}</div>
    ${fks.length ? `<strong style="font-size:13px">Foreign keys</strong><ul class="fk-list">${fks.map(([c, to]) => `<li>${c} → ${to}</li>`).join("")}</ul>` : ""}
    ${form ? `<form id="addForm"><strong style="display:block;margin-top:14px;font-size:13px">Add a record</strong>${form}<button class="btn primary">Add to ${t.toUpperCase()}</button></form>`
      : `<p class="muted" style="font-size:13px">${t === "rides" ? "Records are created when a passenger books a ride." : "Records are created when a driver completes a ride."}</p>`}`;
  $("#addForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
      const r = await api("/api/" + t, { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
      toast(`Added: ${m.pk} = ${r[m.pk]}`);
      loadTable(r[m.pk]);
    } catch (err) { toast(err.message, true); }
  });
}

/* =========================== ADMIN: REPORTS =========================== */
function highlightSql(sql) {
  return esc(sql)
    .replace(/'[^']*'|:\w+/g, m => `<span class="str">${m}</span>`)
    .replace(/\b(SELECT|FROM|JOIN|ON|WHERE|AND|GROUP BY|ORDER BY|AS|COUNT|SUM|DISTINCT|DESC|strftime)\b/g, '<span class="kw">$1</span>');
}
async function loadReports() {
  const month = $("#monthSelect").value;
  const r = await api("/api/reports/driver-earnings" + (month ? "?month=" + month : ""));
  $("#monthSelect").innerHTML = r.months.map(m => `<option value="${m}" ${m === r.month ? "selected" : ""}>${fmtMonth(m)}</option>`).join("");
  const max = Math.max(1, ...r.rows.map(x => x.earnings_kzt));
  $("#earnings").innerHTML = `<h3>${fmtMonth(r.month)}</h3><div class="muted" style="font-size:13px">Total: <b>${money(r.rows.reduce((s, x) => s + x.earnings_kzt, 0))}</b> · the top driver gets a bonus</div>
    <div class="bars">${r.rows.map((x, i) => `<div class="bar-row ${i === 0 ? "top" : ""}">
      <div class="name">${esc(x.full_name)}${i === 0 ? '<span class="bonus">bonus</span>' : ""}<small>${x.rides} rides</small></div>
      <div class="bar-track"><div class="bar-fill" style="width:0" data-w="${(x.earnings_kzt / max) * 100}%"></div></div>
      <div class="val">${money(x.earnings_kzt)}</div></div>`).join("") || '<p class="muted">No payments this month</p>'}</div>`;
  requestAnimationFrame(() => $$("#earnings .bar-fill").forEach(el => (el.style.width = el.dataset.w)));
  $("#sqlBox").innerHTML = highlightSql(r.sql);
  $("#copySql").onclick = () => navigator.clipboard?.writeText(r.sql).then(() => toast("SQL copied"));
  $("#topPickups").innerHTML = `<h3>Top pickup points</h3><ul class="mini-list">${r.top_pickups.map(p => `<li><span>${esc(p.place)}</span><b>${p.rides}</b></li>`).join("")}</ul>`;
  const cash = r.methods.find(m => m.method === "cash") || { n: 0, total: 0 }, card = r.methods.find(m => m.method === "card") || { n: 0, total: 0 };
  const tot = (cash.n + card.n) || 1;
  $("#methods").innerHTML = `<h3>Cash or card</h3>
    <div class="split"><i style="width:${card.n / tot * 100}%;background:var(--blue)"></i><i style="width:${cash.n / tot * 100}%;background:var(--orange-2)"></i></div>
    <ul class="mini-list"><li><span><i class="dot a"></i> Card · ${card.n}</span><b>${money(card.total)}</b></li><li><span><i class="dot b"></i> Cash · ${cash.n}</span><b>${money(cash.total)}</b></li></ul>`;
  $("#unpaid").innerHTML = `<h3>Completed but unpaid</h3>
    ${r.unpaid.length ? `<ul class="mini-list">${r.unpaid.map(u => `<li><span>ride #${u.ride_id}</span><b>${money(u.price)}</b></li>`).join("")}</ul>
      <p class="muted" style="font-size:13px;margin-top:10px">Waiting for a second payment.</p>`
      : '<p class="muted">No unpaid rides.</p>'}`;
}
$("#monthSelect").addEventListener("change", loadReports);

/* =========================== ADMIN: ACCESS & ROLES =========================== */
const MATRIX = [
  ["PASSENGERS", "Own profile; signs up (create)", "Name + phone of the current passenger only", "Read all, add"],
  ["DRIVERS", "Name, phone, rating of own assigned driver", "Own profile", "Read all, add"],
  ["CARS", "Model, color, plate of own assigned car", "Own cars", "Read all, add"],
  ["RIDES", "Own rides: create, cancel while active", "Own assigned rides: complete", "Read all, cancel"],
  ["PAYMENTS", "Own rides: pay again by card", "Own rides: create payment (cash/card)", "Read all, reports"],
];
const AREAS = [
  { t: "Systems Analysis & Requirements", r: "Users, problems, requirements, business rules", li: ["Main action: a passenger books a ride", "Roles: passenger, driver, admin", "A driver has only one active ride at a time", "A passenger has only one active ride at a time"] },
  { t: "Data & Database", r: "ERD, entities, relationships, SQL", li: ["5 tables: PASSENGERS, DRIVERS, CARS, RIDES, PAYMENTS", "PK, FK and CHECK constraints in schema.sql", "The Database tab shows the live tables"] },
  { t: "Application & Development", r: "Core functionality, business logic, UI", li: ["Flask API (app.py) + three role interfaces", "Fare: 500 ₸ + 140 ₸/km, min 800 ₸", "Mountains (Medeu, Shymbulak) +600 ₸, night ×1.2", "The free driver with the best rating is assigned"] },
  { t: "Architecture & Security", r: "Architecture, roles, access control, security", li: ["Browser → REST API → SQLite", "Signed login token, role checked on every request", "Users touch only their own rides (403 otherwise)", "Completing a ride + payment is one transaction"] },
  { t: "Testing, Analytics & Integration", r: "Testing, reports/KPIs, system quality", li: ["Report: driver earnings per month → bonuses", "Finding unpaid rides", "queries.sql: queries for the presentation", "Tests: all drivers busy → 409, wrong role → 403"] },
];
async function renderAccess() {
  $("#matrix").innerHTML = `<thead><tr><th>Table</th><th>Passenger</th><th>Driver</th><th>Admin</th></tr></thead><tbody>${
    MATRIX.map(r => `<tr><td><code>${r[0]}</code></td>${r.slice(1).map(c => `<td class="wrap">${c}</td>`).join("")}</tr>`).join("")}</tbody>`;
  $("#areas").innerHTML = AREAS.map(a => `<div class="card area"><h3>${a.t}</h3><div class="resp">${a.r}</div><ul>${a.li.map(x => `<li>${x}</li>`).join("")}</ul></div>`).join("");
}

/* =========================== START =========================== */
$("#resetBtn").addEventListener("click", async () => {
  if (!confirm("Restore demo data? All records you added will be deleted.")) return;
  await api("/api/reset", { method: "POST" });
  toast("Demo data restored");
  show(state.view);
});

(async function init() {
  if (store.get()) {
    try { await refreshMe(); } catch { store.set(null); state.me = null; }
  }
  renderShell();
  show(location.hash.slice(1) || "");
})();
