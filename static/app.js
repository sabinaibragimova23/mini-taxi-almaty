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

const state = { me: null, places: [], pickup: "", dropoff: "", table: "passengers", rideFilter: "", view: null, loginRole: "passenger", cond: null };

/* =========================== ROLES & NAVIGATION =========================== */
const ROLE_VIEWS = {
  passenger: [["book", "Book"], ["myrides", "My rides"]],
  driver: [["orders", "My orders"], ["earnings", "Earnings"]],
  admin: [["dispatch", "Dispatch"], ["prices", "Prices"], ["db", "Database"], ["reports", "Reports"], ["access", "Access & roles"]],
};
const ROLE_NAME = { passenger: "Passenger", driver: "Driver", admin: "Admin" };
const LOADERS = {
  home: loadHome, login: loadLogin, book: loadBook, myrides: loadMyRides, orders: loadOrders, earnings: loadEarnings,
  dispatch: loadDispatch, prices: loadPrices, db: loadTable, reports: loadReports, access: renderAccess,
};

function renderShell() {
  const me = state.me;
  const views = me ? ROLE_VIEWS[me.role] : [];
  const guestNav = `<button data-view="home">Map</button><span class="nav-label">Log in as</span>`
    + ["passenger", "driver", "admin"].map(r => `<button data-view="login" data-loginrole="${r}">${ROLE_NAME[r]}</button>`).join("")
    + `<button class="signup-tab" data-signup>Sign up</button>`;
  $("#tabs").innerHTML = !me ? guestNav : views.map(([v, label]) => `<button data-view="${v}">${label}${v === "myrides" || v === "orders" || v === "dispatch" ? ' <span class="pill" data-count hidden></span>' : ""}</button>`).join("");
  $("#brandRole").textContent = me ? "Almaty · " + ROLE_NAME[me.role] : "Almaty";
  const chip = $("#userChip");
  chip.hidden = !me;
  if (me) chip.innerHTML = `<span class="avatar ${me.role}">${esc(me.name.slice(0, 1))}</span><span class="who"><b>${esc(me.name)}</b><small>${ROLE_NAME[me.role]}</small></span><button class="btn ghost small" id="logoutBtn">Log out</button>`;
  $("#resetBtn").hidden = !(me && me.role === "admin");
  document.body.dataset.role = me ? me.role : "guest";
}

function show(view) {
  const allowed = state.me ? ROLE_VIEWS[state.me.role].map(v => v[0]) : ["home", "login"];
  if (!allowed.includes(view)) view = allowed[0];
  state.view = view;
  if (view === "login") {   // one login card at a time: the role chosen in the top menu
    $("#view-login").dataset.role = state.loginRole;
    $("#loginTitle").textContent = LOGIN_TEXT[state.loginRole][0];
    $("#loginSub").textContent = LOGIN_TEXT[state.loginRole][1];
  }
  $$("#tabs button").forEach(b => b.classList.toggle("active",
    b.dataset.view === view && (!b.dataset.loginrole || b.dataset.loginrole === state.loginRole)));
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + view));
  if (location.hash !== "#" + view) history.replaceState(null, "", "#" + view);
  LOADERS[view]?.().catch(err => toast(err.message, true));
}
$("#tabs").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.signup !== undefined) return openSignup();
  if (b.dataset.loginrole) state.loginRole = b.dataset.loginrole;
  show(b.dataset.view);
});
const LOGIN_TEXT = {
  passenger: ["Passenger log in", "Book a taxi and see your trips."],
  driver: ["Driver log in", "Complete assigned rides and see your earnings."],
  admin: ["Admin log in", "Tables, rides and monthly reports."],
};
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
  show("home");
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
  const chips = list => `<span class="demo-label">Demo accounts:</span>` + list.map(a => `<button type="button" class="chip" data-login="${esc(a.email || a.phone)}" data-pass="${esc(d.demo_password)}">${esc(a.full_name.split(" ")[0])}</button>`).join("");
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
    if (c.dataset.login) form.login.value = c.dataset.login;
    if (c.dataset.pass) form.password.value = c.dataset.pass;
    form.requestSubmit();
  });
});
function openSignup() {
  openModal(`
  <h2>Create an account</h2><p class="muted">Adds a row to PASSENGERS.</p>
  ${passengerFields()}
  <div class="actions"><button class="btn ghost" value="cancel" formnovalidate>Cancel</button><button class="btn primary">Sign up</button></div>`,
  async fd => { const r = await api("/api/signup", { method: "POST", body: Object.fromEntries(fd) }); await afterLogin(r.token); });
}
$("#signupBtn").addEventListener("click", openSignup);
document.addEventListener("click", e => {
  if (e.target.closest("[data-goto-login]")) { e.preventDefault(); state.loginRole = "passenger"; show("login"); }
  if (e.target.closest("[data-goto-signup]")) { e.preventDefault(); openSignup(); }
});

function passengerFields() {
  return `<label class="field"><span>full_name</span><input type="text" name="full_name" placeholder="e.g. Aidana Serikova" required></label>
    <label class="field"><span>phone</span><input type="tel" name="phone" placeholder="+7 701 123 45 67" required></label>
    <label class="field"><span>email (used to log in)</span><input type="email" name="email" placeholder="name@mail.kz" required></label>
    <label class="field"><span>password (min 6)</span><input type="password" name="password" minlength="6" autocomplete="new-password" required></label>`;
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

/* =========================== MAP (Leaflet + OpenStreetMap, no API key) =========================== */
let homeMap = null, bookMap = null;

function makeMap(el) {
  if (typeof L === "undefined") {
    el.innerHTML = `<p class="muted" style="padding:24px">The map could not be loaded. Check your internet connection and reload the page.</p>`;
    return null;
  }
  const map = L.map(el, { zoomControl: false }).setView([43.2389, 76.8897], 12);
  L.control.zoom({ position: "bottomright" }).addTo(map);   // top-left is taken by the card on the home page
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
  return { map, layer: L.layerGroup().addTo(map), fitted: false };
}
function fitOnce(m) {
  m.map.invalidateSize();   // the map was hidden while the page was on another tab
  if (!m.fitted && state.places.length) {
    m.map.fitBounds(state.places.map(p => [p.lat, p.lng]), { padding: [30, 30] });
    m.fitted = true;
  }
}
const inAccident = p => state.cond && state.cond.accident_district && state.cond.accident_district === p.district;
function pointStyle(role, hot) {
  const s = { radius: 7, weight: 2.5, color: "#1F4E79", fillColor: "#fff", fillOpacity: 1 };
  if (role === "a") Object.assign(s, { radius: 10, color: "#fff", fillColor: "#4472C4" });
  if (role === "b") Object.assign(s, { radius: 10, color: "#fff", fillColor: "#E07A2E" });
  if (hot) Object.assign(s, { color: "#c0392b", weight: 4, radius: s.radius + 2 });   // district with an accident
  return s;
}

/* home page: all pickup points, click a point to read about it */
function drawHomeMap() {
  homeMap ||= makeMap($("#homeMap"));
  if (!homeMap) return;
  fitOnce(homeMap);
  homeMap.layer.clearLayers();
  for (const p of state.places) {
    const hot = inAccident(p);
    L.circleMarker([p.lat, p.lng], pointStyle("", hot)).addTo(homeMap.layer)
      .bindTooltip(esc(p.name), { direction: "top", offset: [0, -6] })
      .bindPopup(`<b>${esc(p.name)}</b><br><span class="muted">${esc(p.district)} district${hot ? " · accident" : ""}</span><br><a href="#login" data-goto-login>Log in to book a taxi</a>`);
  }
}

/* booking page: click the pickup point, then the drop-off point */
function drawMap() {
  bookMap ||= makeMap($("#map"));
  if (!bookMap) return;
  fitOnce(bookMap);
  const { layer } = bookMap;
  layer.clearLayers();
  const a = state.places.find(p => p.name === state.pickup), b = state.places.find(p => p.name === state.dropoff);
  if (a && b) L.polyline([[a.lat, a.lng], [b.lat, b.lng]], { color: "#1F4E79", weight: 4, dashArray: "9 8" }).addTo(layer);
  for (const p of state.places) {
    const role = p.name === state.pickup ? "a" : p.name === state.dropoff ? "b" : "";
    L.circleMarker([p.lat, p.lng], pointStyle(role, inAccident(p))).addTo(layer)
      .bindTooltip(esc(p.name), { permanent: !!role, direction: "top", offset: [0, -8], className: "pt-tip " + role })
      .on("click", () => pickPlace(p.name));
  }
}
function pickPlace(name) {
  if (!state.pickup || (state.pickup && state.dropoff)) { state.pickup = name; state.dropoff = ""; }
  else if (name !== state.pickup) state.dropoff = name;
  syncRoute();
}

/* traffic, accident and weather: shown on the map pages, set by the admin / the weather service */
const WEATHER_TXT = { clear: "Clear", rain: "Rain", snow: "Snow" };
const WEATHER_ICO = { clear: "☀", rain: "🌧", snow: "❄" };
const TRAFFIC_TXT = { free: "Roads are free", moderate: "Moderate traffic", heavy: "Heavy traffic" };
function condBarHtml(c) {
  if (!c) return "";
  const parts = [
    `<span class="cchip w-${c.weather}">${WEATHER_ICO[c.weather]} ${WEATHER_TXT[c.weather]}${c.temp != null ? " " + Math.round(c.temp) + "°C" : ""}</span>`,
    `<span class="cchip t-${c.traffic}"><i></i>${TRAFFIC_TXT[c.traffic]}</span>`,
  ];
  if (c.accident_district) parts.push(`<span class="cchip acc">⚠ Accident: ${esc(c.accident_district)} district</span>`);
  const extra = c.traffic !== "free" || c.accident_district || c.weather !== "clear";
  parts.push(`<span class="cnote">${extra ? "Extra charges may apply to your ride" : "No extra charges for traffic or weather right now"}</span>`);
  return parts.join("");
}
function renderCondBars() {
  for (const id of ["#condHome", "#condBook"]) $(id).innerHTML = condBarHtml(state.cond);
}
async function loadConditions() {
  state.cond = await api("/api/conditions");
  renderCondBars();
  return state.cond;
}
async function ensurePlaces() {
  if (state.places.length) return;
  state.places = await api("/api/places");
  $("#pickupSelect").innerHTML = placeOptions("Pickup point");
  $("#dropoffSelect").innerHTML = placeOptions("Where to?");
}
async function loadHome() {
  await ensurePlaces();
  await loadConditions().catch(() => {});
  drawHomeMap();
}
/* every minute: if the admin or the weather changed something, update the map and the price */
setInterval(async () => {
  if (document.hidden || !["home", "book"].includes(state.view)) return;
  const before = JSON.stringify(state.cond);
  try { await loadConditions(); } catch { return; }
  if (JSON.stringify(state.cond) === before) return;
  if (state.view === "home") drawHomeMap(); else syncRoute();
}, 60000);

/* =========================== PASSENGER: BOOK =========================== */
function placeOptions(placeholder) {
  const byDistrict = {};
  for (const p of state.places) (byDistrict[p.district] ||= []).push(p);
  return `<option value="">${placeholder}</option>` + Object.entries(byDistrict).map(([d, ps]) =>
    `<optgroup label="${d} District">${ps.map(p => `<option>${esc(p.name)}</option>`).join("")}</optgroup>`).join("");
}

async function loadBook() {
  await ensurePlaces();
  await loadConditions().catch(() => {});
  $("#greeting").textContent = `Where to, ${state.me.name.split(" ")[0]}?`;
  syncRoute();
  await renderActiveBanner();
}

const penaltyDialog = $("#penaltyDialog");
const agreePenaltyBtn = $("#agreePenaltyBtn");

// Функция для показа предупреждения с проверкой localStorage
function showPenaltyModalIfNeeded(progressPercent, rideId) {
    // Проверяем, нажимал ли пользователь "I agree" для этой конкретной поездки
    const agreedKey = `penalty_agreed_${rideId}`;
    const alreadyAgreed = localStorage.getItem(agreedKey) === "true";

    if (progressPercent >= 80 && penaltyDialog && !penaltyDialog.open && !alreadyAgreed) {
        penaltyDialog.showModal();
    }
}

// Обработчик нажатия на кнопку "I agree"
if (agreePenaltyBtn) {
    agreePenaltyBtn.addEventListener("click", () => {
        if (penaltyDialog) {
            // Нам нужно знать ID текущей поездки, чтобы сохранить статус
            // Получаем его из активного баннера или глобального состояния
            const activeRideId = penaltyDialog.dataset.currentRideId;
            if (activeRideId) {
                localStorage.setItem(`penalty_agreed_${activeRideId}`, "true");
            }
            penaltyDialog.close();
        }
    });
}
let hadActive = null;
let rideTimers = {};

async function renderActiveBanner() {
  const rides = await api("/api/my/rides");
  const active = rides.find(r => r.status === "requested");
  setCount(active ? 1 : 0);
  if (hadActive && !active) {
    const done = rides.find(r => r.ride_id === hadActive);
    if (done) toast(done.status === "completed" ? `Ride #${done.ride_id} completed, payment ${LABEL_TXT[done.last_payment_status] || ""}` : `Ride #${done.ride_id} ${LABEL_TXT[done.status]}`, done.last_payment_status === "failed");
  }
  hadActive = active ? active.ride_id : null;
  $("#activeBanner").innerHTML = active ? rideBanner(active) : "";
  $("#orderBtn").dataset.blocked = active ? "1" : "";
  updateOrderBtn();
}

function calcLateCancelFee(price) {
  const numPrice = Number(price);
  if (!Number.isFinite(numPrice) || numPrice <= 0) {
    return 200;
  }
  if (numPrice > 1000) {
    return Math.round(numPrice * 0.2);
  }
  return 200;
}

function rideBanner(r) {
  const initialEtaMin = 3 + (r.ride_id % 3);
  const totalSeconds = initialEtaMin * 60;

  const storageKey = `ride_start_${r.ride_id}`;
  let startTime = localStorage.getItem(storageKey);
  if (!startTime) {
    startTime = Date.now();
    localStorage.setItem(storageKey, startTime);
  } else {
    startTime = Number(startTime);
  }

  const secondsElapsed = Math.floor((Date.now() - startTime) / 1000);
  const progress = Math.min(100, Math.floor((secondsElapsed / totalSeconds) * 100));
  if (penaltyDialog) {
    penaltyDialog.dataset.currentRideId = r.ride_id; // Сохраняем ID текущей поездки в элемент
}
showPenaltyModalIfNeeded(progress, r.ride_id);

  const remainingSec = Math.max(0, totalSeconds - secondsElapsed);
  const currentEta = Math.ceil(remainingSec / 60);

  const isArrived = progress >= 100 || currentEta === 0;
  const isLateCancel = progress >= 80 && !isArrived;

  const penaltyAmount = calcLateCancelFee(r.price);
  const driverComp = Math.round(penaltyAmount * 0.75);
  const companyRisk = Math.max(0, penaltyAmount - driverComp);

  const topStatusText = isArrived
    ? "driver is waiting for you"
    : `driver on the way (${progress}% of route)`;

  let actionHtml = "";
  if (isArrived) {
    actionHtml = `<span style="color:#2e7d32; font-weight:600; font-size:12px;">Driver is waiting for you</span>`;
  } else if (isLateCancel) {
    actionHtml = `
      <div style="color:#d9534f; font-weight:600; font-size:11px; margin-bottom:4px;">
        Driver is arriving, please wait (fee ${penaltyAmount} ₸)
      </div>
      <button class="btn danger small" data-act="cancel" data-id="${r.ride_id}" data-penalty="${penaltyAmount}" data-driver-comp="${driverComp}" data-company-risk="${companyRisk}">
        Cancel (${penaltyAmount} ₸)
      </button>
    `;
  } else {
    actionHtml = `<button class="btn danger small" data-act="cancel" data-id="${r.ride_id}" data-penalty="0">Cancel ride</button>`;
  }

  return `<div class="card confirm" style="display: flex; justify-content: space-between; align-items: center;">
    <div style="flex: 1;">
      <div>
        <div class="ride-id">ride #${r.ride_id}</div>
        ${esc(r.start_time)}
        <span class="live"><i></i>${topStatusText}</span>
      </div>
      <h3 style="margin: 6px 0;">${esc(r.driver_name)} <span class="stars">★ ${Number(r.driver_rating).toFixed(1)}</span> <span class="muted" style="font-size:12px">(${esc(r.car_model)}, ${esc(r.car_color || "")})  ${plate(r.plate_number)}</span></h3>
      <div class="muted"><b>${esc(r.pickup_address)}</b> → ${esc(r.dropoff_address)}</div>
    </div>
    <div style="text-align: right; min-width: 230px;">
      <div class="eta" style="margin-bottom: 6px;">${isArrived ? "Driver is waiting for you" : `arrives in ~${currentEta} min`}</div>
      <div>${actionHtml}</div>
    </div>
  </div>`;

}



async function syncRoute() {
  $("#pickupSelect").value = state.pickup;
  $("#dropoffSelect").value = state.dropoff;
  $("#mapTip").textContent = !state.pickup
    ? "Click the pickup point, then the drop-off point"
    : !state.dropoff
      ? "Now choose where to go"
      : `${state.pickup} → ${state.dropoff}`;
  drawMap();

  const box = $("#quoteBox");
  const orderBtn = $("#orderBtn");
  state.quoteOk = false;

  const hasUnpaidPenalty = Boolean(window.hasUnpaidPenalty);
  if (hasUnpaidPenalty) {
    orderBtn.dataset.blocked = "1";
    orderBtn.disabled = false; // Обязательно false, чтобы клик доходил до формы
    orderBtn.textContent = "Pay penalty to order";
  } else {
    orderBtn.dataset.blocked = "";
    orderBtn.disabled = !state.quoteOk;
    orderBtn.textContent = "Book a taxi";
  }

  if (!state.pickup || !state.dropoff) {
    box.innerHTML = `<div class="quote-empty">Choose a route to see the price</div>`;
    return updateOrderBtn();
  }

  try {
    const q = await api("/api/quote", {
      method: "POST",
      body: { pickup: state.pickup, dropoff: state.dropoff },
    });

    const basePrice = Number(q.price) || 0;
    const unpaidPenalty = hasUnpaidPenalty ? calcLateCancelFee(basePrice) : 0;
    const driverComp = Math.round(unpaidPenalty * 0.75);
    const companyRisk = Math.max(0, unpaidPenalty - driverComp);
    const finalPrice = basePrice + unpaidPenalty;

    const penaltyLine = unpaidPenalty > 0
      ? `<li class="extra"><span>Late cancel penalty (driver ${driverComp} ₸ / company risk ${companyRisk} ₸)</span><b>+${money(unpaidPenalty)}</b></li>`
      : "";

    box.innerHTML = `<div class="quote-wrap">
      <div class="quote-body">
        <div class="quote-meta">${q.distance_km} km · ~${q.minutes} min ride</div>
        <div class="quote-price">${money(finalPrice)}</div>
      </div>
      <ul class="price-lines">${q.lines.map(l => `<li class="${l.rule && !["base", "per_km"].includes(l.rule) ? "extra" : ""}">
        <span>${esc(l.label)}</span><b>${l.kzt >= 0 && l.rule && !["base", "per_km"].includes(l.rule) ? "+" : ""}${money(l.kzt)}</b></li>`).join("")}
        ${penaltyLine}
        <li class="total"><span>Total</span><b>${money(finalPrice)}</b></li></ul>
    </div>`;
    state.quoteOk = true;
  } catch (err) {
    box.innerHTML = `<div class="quote-empty">${esc(err.message)}</div>`;
  }
  updateOrderBtn();
}

function updateOrderBtn() {
    const btn = $("#orderBtn");
    const blocked = btn.dataset.blocked === "1";
    btn.disabled = blocked ? false : !state.quoteOk;
    btn.textContent = blocked ? "You already have a ride" : "Book a taxi";
}

$("#pickupSelect").addEventListener("change", e => { state.pickup = e.target.value; syncRoute(); });
$("#dropoffSelect").addEventListener("change", e => { state.dropoff = e.target.value; syncRoute(); });
$("#swapBtn").addEventListener("click", () => { [state.pickup, state.dropoff] = [state.dropoff, state.pickup]; syncRoute(); });

$("#orderForm").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = $("#orderBtn");

  if (btn.textContent.includes("Pay penalty") || btn.dataset.blocked === "1" || window.hasUnpaidPenalty) {
      const payDlg = $("#payPenaltyDialog");
      if (payDlg) {
          payDlg.showModal();
      } else {
          alert("Please pay your cancellation penalty first.");
      }
      return; // Стоп! Заказ не уйдет на сервер.
  }

  if (btn.dataset.blocked === "1") {
    alert("You already have an active ride! You cannot book a second one.");
    return;
  }
  
  const hasUnpaidPenalty = window.hasUnpaidPenalty || false; 

    const orderBtn = $("#orderBtn");
    if (hasUnpaidPenalty) {
        orderBtn.dataset.blocked = "1";
        orderBtn.disabled = false; // Оставляем кликабельной для вызова модалки
        orderBtn.textContent = "Pay penalty to order";
    }

  btn.disabled = true;
  btn.textContent = "Finding a driver...";
   try {
    const r = await api("/api/rides", { method: "POST", body: { pickup: state.pickup, dropoff: state.dropoff } });
    toast(`Ride #${r.ride_id} booked`);
    // Сохраняем ID поездки и открываем модалку предупреждения сразу при заказе
    if (penaltyDialog) {
        penaltyDialog.dataset.currentRideId = r.ride_id;
        penaltyDialog.showModal();
    }
    
    state.pickup = "";
    state.dropoff = "";
    await syncRoute();
    await renderActiveBanner();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    alert("Warning: " + (err.message || "Failed to book a ride"));
    toast(err.message, true);
    updateOrderBtn();
  }
});

const payPenaltyDialog = $("#payPenaltyDialog");
const payPenaltyBtn = $("#payPenaltyBtn");
const closePenaltyModal = $("#closePenaltyModal");

if (closePenaltyModal) {
    closePenaltyModal.addEventListener("click", () => {
        payPenaltyDialog.close();
    });
}

if (payPenaltyBtn) {
    payPenaltyBtn.addEventListener("click", async () => {
        try {
            // Здесь отправляется запрос на бэкенд для списания/оплаты штрафа
            // Например: await api("/api/pay-penalty", { method: "POST" });
            
            toast("Penalty paid successfully! You can now book a ride.");
            window.hasUnpaidPenalty = false;
            
            // Снимаем блокировку с кнопки заказа
            const orderBtn = $("#orderBtn");
            orderBtn.dataset.blocked = "";
            orderBtn.disabled = false;
            orderBtn.textContent = "Book a taxi";
            
            payPenaltyDialog.close();
            syncRoute(); // Пересчитываем маршрут
        } catch (err) {
            toast(err.message, true);
        }
    });
}

/* =========================== PASSENGER: MY RIDES =========================== */
// five clickable stars (rendered 5..1 and reversed with CSS, so hover lights the stars up to the one under the mouse)
function rateButtons(id) {
  return `<span class="rate" title="Rate this trip">${[5, 4, 3, 2, 1].map(v =>
    `<button type="button" data-act="rate" data-id="${id}" data-v="${v}" aria-label="${v} of 5">★</button>`).join("")}</span>`;
}
function starsView(n) {
  return n ? `<span class="stars" title="${n} of 5">${"★".repeat(n)}<span class="off">${"★".repeat(5 - n)}</span></span>` : "—";
}

function canEditReview(r) {
  if (!r.rated_at) return false;

  const submittedAt = new Date(r.rated_at).getTime();

  return Number.isFinite(submittedAt) &&
    Date.now() < submittedAt + 60 * 60 * 1000;
}

function parseFeedbackTags(raw) {
  try {
    const tags = Array.isArray(raw) ? raw : JSON.parse(raw || "[]");
    return Array.isArray(tags) ? tags : [];
  } catch {
    return [];
  }
}

function editReviewButton(r) {
  return canEditReview(r)
    ? ` <button type="button" class="btn ghost small"
        data-act="edit-review" data-id="${r.ride_id}">Edit review</button>`
    : "";
}

const POSITIVE_FEEDBACK_OPTIONS = [
  "Polite driver", "Clean car", "Safe driving",
  "Arrived on time", "Comfortable ride", "Friendly communication"
];
const IMPROVEMENT_FEEDBACK_OPTIONS = [
  "Rude driver", "Dirty car", "Unsafe driving",
  "Driver was late", "Uncomfortable ride"
];
function feedbackTagsView(raw) {
  let tags = [];
  try { tags = Array.isArray(raw) ? raw : JSON.parse(raw || "[]"); } catch (_) {}
  if (!Array.isArray(tags) || !tags.length) return "";
  return `<div class="feedback-tags">${tags.map(t => `<span class="feedback-tag">${esc(t)}</span>`).join("")}</div>`;
}
async function loadMyRides() {
  const [rides] = await Promise.all([api("/api/my/rides"), refreshMe()]);

  // Do not refresh the history while the passenger is writing a comment
  if (document.querySelector(".rating-comment-form")) return;
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
  $("#pHistory").innerHTML = `<thead><tr>
    <th>#</th>
    <th>Time</th>
    <th>Route</th>
    <th>Driver</th>
    <th>Car</th>
    <th>Price</th>
    <th>Status</th>
    <th>Payment</th>
    <th>Rating</th>
    <th>Feedback</th>
  </tr></thead><tbody>${
    rides.map(r => `<tr>
      <td>${r.ride_id}</td>
      <td>${esc(r.start_time)}</td>
      <td class="wrap">${esc(r.pickup_address)} → ${esc(r.dropoff_address)}</td>
      <td>${esc(r.driver_name)}</td>
      <td>${esc(r.car_model)}</td>
      <td><b>${money(r.price)}</b></td>
      <td>${badge(r.status)}</td>
      <td>${r.last_payment_status ? badge(r.last_payment_status) + ` <span class="muted">${LABEL_TXT[r.last_payment_method]}</span>` : "—"}</td>
      <td>${r.status !== "completed" ? "—" : r.ride_rating
        ? starsView(r.ride_rating) + editReviewButton(r)
        : rateButtons(r.ride_id)}</td>
      <td class="wrap">${feedbackTagsView(r.feedback_tags)}${r.ride_comment ? `<div>${esc(r.ride_comment)}</div>` : (!r.feedback_tags ? "—" : "")}</td>
    </tr>`).join("")
    || '<tr><td colspan="10" class="muted">No trips yet</td></tr>'}</tbody>`;
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
    <div class="status ${active ? "busy" : state.me.online ? "free" : "off"}"><i></i>${active ? "On a ride" : state.me.online ? "Online · waiting" : "Offline"}</div>
    <button class="btn ${state.me.online ? "ghost" : "primary"}" data-act="${state.me.online ? "offline" : "online"}">${state.me.online ? "Go offline" : "Go online"}</button>`;
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
    : state.me.online
      ? `<div class="empty waiting"><span class="pulse"></span><b>No order yet</b><br>Rides go to the online driver with the highest rating.</div>`
      : `<div class="empty waiting"><b>You are offline</b><br>Press Go online to start getting orders.</div>`;
  const unpaid = rides.filter(r => r.status === "completed" && r.last_payment_status === "failed");
  $("#dUnpaid").innerHTML = unpaid.map(r => `
    <div class="card alert"><b>Ride #${r.ride_id}: card declined.</b> ${esc(r.passenger_name)} · ${money(r.price)}
      <button class="btn primary small" data-act="pay" data-id="${r.ride_id}">Got cash</button></div>`).join("");
  const done = rides.filter(r => r.status !== "requested");
  $("#dHistory").innerHTML = `<thead><tr><th>#</th><th>Time</th><th>Passenger</th><th>Route</th><th>Car</th><th>Price</th><th>Status</th><th>Payment</th><th>Rating</th></tr></thead><tbody>${
    done.map(r => `<tr><td>${r.ride_id}</td><td>${esc(r.start_time)}</td><td>${esc(r.passenger_name)}</td><td class="wrap">${esc(r.pickup_address)} → ${esc(r.dropoff_address)}</td>
      <td>${plate(r.plate_number)}</td><td><b>${money(r.price)}</b></td><td>${badge(r.status)}</td><td>${badge(r.last_payment_status) || "—"}</td>
      <td>${starsView(r.ride_rating)}</td></tr>`).join("")
    || '<tr><td colspan="9" class="muted">No rides yet</td></tr>'}</tbody>`;
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
/* =========================== PRICES =========================== */
function fareValue(r) {
  if (r.kind === "multiplier") return `×${Number(r.amount)}`;
  if (r.kind === "per_km") return `${money(r.amount)} / km`;
  if (r.kind === "surcharge") return `+${money(r.amount)}`;
  return money(r.amount);
}

/* passenger: panel with all prices and extra charges */
async function renderPricePanel() {
  const fares = await api("/api/fares");
  const main = fares.filter(r => ["fixed", "per_km", "minimum"].includes(r.kind));
  const extra = fares.filter(r => !["fixed", "per_km", "minimum"].includes(r.kind));
  const row = r => `<tr><td><b>${esc(r.name)}</b></td><td class="num">${fareValue(r)}</td><td class="muted">${esc(r.applies_to)}</td></tr>`;
  $("#pricePanel").innerHTML = `
    <div class="price-head"><h2 id="priceDialogTitle">Prices and extra charges</h2><span class="muted">All prices in tenge. The price is fixed when you book.</span></div>
    <div class="price-cols">
      <div><h3>Main fare</h3><table class="price-table">${main.map(row).join("")}</table></div>
      <div><h3>Extra charges</h3><table class="price-table">${extra.map(row).join("") || '<tr><td class="muted">No extra charges right now</td></tr>'}</table></div>
    </div>
    <p class="muted" style="font-size:13px;margin:12px 0 0">Extra charges add up: a night ride from the airport pays the airport surcharge and the night fare. Traffic, accidents and weather are added while they last; all extra charges together never raise the price more than ×2.</p>`;
}

const pricesBtn = $("#pricesBtn");
const priceDialog = $("#priceDialog");
const priceDialogClose = $("#priceDialogClose");

if (pricesBtn && priceDialog && priceDialogClose) {
  pricesBtn.addEventListener("click", async () => {
    try {
      await renderPricePanel();
      priceDialog.showModal();
    } catch (err) {
      toast(err.message, true);
    }
  });

  priceDialogClose.addEventListener("click", () => {
    priceDialog.close();
  });

  priceDialog.addEventListener("click", e => {
    if (e.target.id === "priceDialog") {
      priceDialog.close();
    }
  });
}
$("#priceDialogClose").addEventListener("click", () => $("#priceDialog").close());
// a click on the dark background outside the window closes it too
$("#priceDialog").addEventListener("click", e => { if (e.target.id === "priceDialog") e.target.close(); });

/* admin: change prices, switch extra charges on and off */
async function renderCondAdmin() {
  const c = await loadConditions();
  const opt = (v, t, cur) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(t)}</option>`;
  const source = c.weather_mode !== "auto" ? "set by the admin"
    : c.weather_source === "internet" ? "Open-Meteo, updated every 10 minutes" : "not available right now, treated as clear";
  $("#condAdmin").innerHTML = `
    <div class="cond-admin-head"><h3>Traffic, accidents and weather</h3>
      <span class="muted">Passengers see this on the map. The matching extra charges are in the table below.</span></div>
    <div class="cond-form">
      <label class="field"><span>Traffic</span><select id="condTraffic">${opt("free", "Free roads", c.traffic)}${opt("moderate", "Moderate", c.traffic)}${opt("heavy", "Heavy", c.traffic)}</select></label>
      <label class="field"><span>Accident in district</span><select id="condAccident">${opt("", "None", c.accident_district)}${c.districts.map(d => opt(d, d, c.accident_district)).join("")}</select></label>
      <label class="field"><span>Weather</span><select id="condWeather">${opt("auto", "Auto (from the internet)", c.weather_mode)}${opt("clear", "Clear", c.weather_mode)}${opt("rain", "Rain", c.weather_mode)}${opt("snow", "Snow", c.weather_mode)}</select></label>
      <button class="btn blue" id="condSave" type="button">Save</button>
    </div>
    <div class="cond-bar">${condBarHtml(c)}</div>
    <p class="muted" style="font-size:12.5px;margin:8px 0 0">Weather source: ${source}. All extra charges together never raise a price more than ×2.</p>`;
}
$("#condAdmin").addEventListener("click", async e => {
  if (e.target.id !== "condSave") return;
  try {
    await api("/api/conditions", { method: "POST", body: {
      traffic: $("#condTraffic").value, accident_district: $("#condAccident").value, weather_mode: $("#condWeather").value } });
    toast("Saved. New bookings use these conditions now.");
    await renderCondAdmin();
    await renderPriceExample();
  } catch (err) { toast(err.message, true); }
});

async function loadPrices() {
  await renderCondAdmin();
  const rules = await api("/api/fare_rules");
  const core = ["base", "per_km", "minimum"];
  $("#priceRules").innerHTML = `<thead><tr><th>Price</th><th>When it applies</th><th>Type</th><th>Amount</th><th>On</th><th>Last change</th><th></th></tr></thead><tbody>${
    rules.map(r => `<tr data-rule="${esc(r.rule_key)}">
      <td><b>${esc(r.name)}</b><div class="muted mono-sm">${esc(r.rule_key)}</div></td>
      <td class="wrap">${esc(r.applies_to)}</td>
      <td><span class="badge ${r.kind === "multiplier" ? "card" : "cash"}">${r.kind}</span></td>
      <td><input type="number" class="amount-input" value="${Number(r.amount)}" min="${r.kind === "multiplier" ? 1 : 1}" max="${r.kind === "multiplier" ? 3 : 100000}" step="${r.kind === "multiplier" ? 0.05 : 10}"> <span class="muted">${r.kind === "multiplier" ? "×" : r.kind === "per_km" ? "₸/km" : "₸"}</span></td>
      <td><input type="checkbox" class="active-input" ${r.active ? "checked" : ""} ${core.includes(r.rule_key) ? 'disabled title="Always on"' : ""}></td>
      <td class="muted">${esc(r.updated_at || "—")}</td>
      <td><button class="btn blue small" data-save-rule="${esc(r.rule_key)}">Save</button></td></tr>`).join("")}</tbody>`;
  await renderPriceExample();
}
async function renderPriceExample() {
  const q = await api("/api/quote", { method: "POST", body: { pickup: "Almaty Airport", dropoff: "Esentai Mall" } });
  $("#priceExample").innerHTML = `<h3>Example right now: Almaty Airport → Esentai Mall</h3>
    <ul class="price-lines">${q.lines.map(l => `<li><span>${esc(l.label)}</span><b>${money(l.kzt)}</b></li>`).join("")}
    <li class="total"><span>Total</span><b>${money(q.price)}</b></li></ul>`;
}
$("#priceRules").addEventListener("click", async e => {
  const b = e.target.closest("[data-save-rule]");
  if (!b) return;
  const tr = b.closest("tr");
  b.disabled = true;
  try {
    const r = await api(`/api/fare_rules/${b.dataset.saveRule}`, { method: "POST", body: {
      amount: Number(tr.querySelector(".amount-input").value),
      active: tr.querySelector(".active-input").checked } });
    toast(`${r.name} saved. New bookings use it now.`);
    loadPrices();
  } catch (err) { toast(err.message, true); b.disabled = false; }
});

async function loadDispatch() {
  const [s, active, hist] = await Promise.all([
    api("/api/stats"),
    api("/api/rides?status=requested"),
    api("/api/rides?limit=150" + (state.rideFilter ? "&status=" + state.rideFilter : "")),
  ]);
  setCount(s.active_rides);
  $("#stats").innerHTML = `
    <div class="stat"><b>${s.free_drivers} / ${s.online_drivers}</b><span>free / online drivers (of ${s.drivers})</span></div>
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
  $("#historyTable").innerHTML = `<thead><tr><th>#</th><th>Time</th><th>Passenger</th><th>Driver</th><th>Route</th><th>Price</th><th>Status</th><th>Payment</th><th>Rating</th><th>Feedback</th></tr></thead><tbody>${
    list.map(r => `<tr><td>${r.ride_id}</td><td>${esc(r.start_time)}</td><td>${esc(r.passenger_name)}</td><td>${esc(r.driver_name)}</td>
      <td class="wrap">${esc(r.pickup_address)} → ${esc(r.dropoff_address)}</td><td><b>${money(r.price)}</b></td><td>${badge(r.status)}</td>
      <td>${r.last_payment_status ? badge(r.last_payment_status) + ` <span class="muted">${LABEL_TXT[r.last_payment_method]}</span>` : "—"}</td>
      <td>${starsView(r.ride_rating)}</td>
      <td class="wrap">${feedbackTagsView(r.feedback_tags)}${r.ride_comment ? `<div>${esc(r.ride_comment)}</div>` : (!r.feedback_tags ? "—" : "")}</td>
      </tr>`).join("")}</tbody>`;
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
  if (e.target.classList.contains("rating-feedback-backdrop")) {
    document.querySelector(".rating-feedback-backdrop")?.remove();
    LOADERS[state.view]?.();
    return;
  }
  const b = e.target.closest("[data-act]");
  if (!b) return;

  const id = b.dataset.id;
  const action = b.dataset.act;

  // Open feedback modal for a new review or an edit.
if (action === "rate" || action === "edit-review") {
  const isEdit = action === "edit-review";
  let rating = Number(b.dataset.v || 0);
  let comment = "";
  let selectedTags = [];

  if (isEdit) {
    const rides = await api("/api/my/rides");
    const ride = rides.find(r => String(r.ride_id) === String(id));

    if (!ride || !ride.ride_rating) {
      toast("Review not found. Refresh the page.", true);
      return;
    }

    if (!canEditReview(ride)) {
      toast("The one-hour editing period has expired.", true);
      LOADERS[state.view]?.();
      return;
    }

    rating = Number(ride.ride_rating);
    comment = ride.ride_comment || "";
    selectedTags = parseFeedbackTags(ride.feedback_tags);
  }

  const required = rating <= 3;
  const options = required ? IMPROVEMENT_FEEDBACK_OPTIONS : POSITIVE_FEEDBACK_OPTIONS;
  const title = isEdit ? "Edit your review" : (required ? "How can we improve?" : "How was your ride?");
  const subtitle = required
    ? "Choose what went wrong, or tell us more below."
    : "Select what you enjoyed. You can also leave a comment.";

  document.querySelector(".rating-feedback-backdrop")?.remove();
  document.body.insertAdjacentHTML("beforeend", `
    <div class="rating-feedback-backdrop" role="presentation">
      <section class="rating-feedback-modal" role="dialog" aria-modal="true" aria-label="Ride feedback">
        <button type="button" class="rating-feedback-close" data-act="cancel-rating" aria-label="Close">×</button>
        <h3>${title}</h3>
        <p class="rating-feedback-subtitle">${subtitle}</p>
        <div class="rating-feedback-stars">${"★".repeat(rating)}<span>${"★".repeat(5-rating)}</span></div>
        <div class="rating-comment-form">
          <strong>${required ? "What could be improved?" : "What did you like?"}</strong>
          <div class="feedback-options">
            ${options.map(option => `<label class="feedback-option"><input type="checkbox" value="${esc(option)}" ${selectedTags.includes(option) ? "checked" : ""}><span>${esc(option)}</span></label>`).join("")}
          </div>
          <label class="rating-comment-label">Additional comment <span class="optional-label">(optional)</span></label>
          <textarea class="rating-comment-input" maxlength="1000" rows="3"
            placeholder="${required ? "Select an option or explain your experience..." : "Share your experience..."}">${esc(comment)}</textarea>
          <div class="rating-comment-actions">
            <button type="button" class="btn primary" data-act="submit-rating" data-id="${id}" data-v="${rating}" data-mode="${isEdit ? "edit" : "new"}">${isEdit ? "Save changes" : "Submit feedback"}</button>
            <button type="button" class="btn ghost" data-act="cancel-rating">Cancel</button>
          </div>
        </div>
      </section>
    </div>
  `);

  document.querySelector(".rating-feedback-modal textarea")?.focus();
  return;
}

  // Close feedback modal
  if (action === "cancel-rating") {
    document.querySelector(".rating-feedback-backdrop")?.remove();
    LOADERS[state.view]?.();
    return;
  }

  b.disabled = true;

  try {
    if (action === "complete") {
      await api(`/api/rides/${id}/complete`, {
        method: "POST",
        body: { method: b.dataset.m }
      });

      toast(`Ride #${id} completed, payment saved`);

    } else if (action === "fail") {
      await api(`/api/rides/${id}/complete`, {
        method: "POST",
        body: { method: "card", simulate_fail: true }
      });

      toast("Card declined, saved in PAYMENTS as failed", true);

    } else if (action === "cancel") {
      await api(`/api/rides/${id}/cancel`, {
        method: "POST"
      });

      if (state.view === "book") hadActive = null;

      const penalty = Number(b.dataset.penalty || 0);
      const driverComp = Number(b.dataset.driverComp || 0);
      const companyRisk = Number(b.dataset.companyRisk || 0);

      if (penalty > 0) {
        localStorage.setItem(`ride_cancel_penalty_${id}`, JSON.stringify({
          rideId: id,
          penalty,
          driverComp,
          companyRisk,
          timestamp: Date.now()
        }));
        toast(
          `Ride #${id} cancelled. Late cancellation fee: ${penalty} ₸ (driver compensation: ${driverComp} ₸, company risk/loss: ${companyRisk} ₸).`,
          true
        );
      } else {
        toast(`Ride #${id} cancelled`);
      }

    } else if (action === "submit-rating") {
      const form = b.closest(".rating-comment-form");
      const textarea = form.querySelector("textarea");
      const comment = textarea.value.trim();
      const feedback_tags = [...form.querySelectorAll(".feedback-option input:checked")].map(input => input.value);
      if (!comment && feedback_tags.length === 0 && Number(b.dataset.v) <= 3) {
        toast("Select at least one option or leave a comment", true);
        textarea.focus();
        b.disabled = false;
        return;
      }
      const isEdit = b.dataset.mode === "edit";
      const r = await api(`/api/rides/${id}/rate`, {
        method: isEdit ? "PUT" : "POST",
        body: { rating: Number(b.dataset.v), comment, feedback_tags }
      });
      toast(isEdit
        ? `Review updated. Driver rating now ${Number(r.driver_rating).toFixed(1)}`
        : `Thanks! Rated ${r.ride_rating}/5 · driver rating now ${Number(r.driver_rating).toFixed(1)}`);

    } else if (action === "pay") {
      const r = await api(`/api/rides/${id}/pay`, {
        method: "POST"
      });

      toast(`Ride #${id} paid by ${r.method}`);

    } else if (action === "online") {
      await api("/api/driver/online", { method: "POST" });
      toast("You are online. New orders can come to you.");

    } else if (action === "offline") {
      await api("/api/driver/offline", { method: "POST" });
      toast("You are offline. You will not get new orders.");
    }

    document.querySelector(".rating-feedback-backdrop")?.remove();
    document.querySelector(".rating-comment-form")?.remove();
    LOADERS[state.view]?.();

  } catch (err) {
    toast(err.message, true);
    b.disabled = false;
  }
});

/* =========================== ADMIN: DATABASE =========================== */
const TABLES = {
  passengers: { desc: "People who order rides", cols: ["passenger_id", "full_name", "phone", "email", "registration_date", "password_hash"], pk: "passenger_id", fk: {}, why: "Passenger details are stored once, not in every ride." },
  drivers: { desc: "People who drive the cars", cols: ["driver_id", "full_name", "phone", "email", "license_number", "rating", "password_hash"], pk: "driver_id", fk: {}, why: "Driver details and rating are stored once." },
  cars: { desc: "Cars used for rides", cols: ["car_id", "driver_id", "plate_number", "model", "color"], pk: "car_id", fk: { driver_id: "DRIVERS" }, why: "A driver can change cars or have two, so car data is kept separately from the driver (see driver 3)." },
  rides: { desc: "One row for every ride", cols: ["ride_id", "passenger_id", "driver_id", "car_id", "pickup_address", "dropoff_address", "start_time", "status", "price", "ride_rating", "ride_comment", "feedback_tags"], pk: "ride_id", fk: { passenger_id: "PASSENGERS", driver_id: "DRIVERS", car_id: "CARS" }, why: "This is the main action. It connects a passenger, a driver and a car." },
  fare_rules: { desc: "All prices and extra charges", cols: ["rule_key", "name", "kind", "amount", "applies_to", "active", "updated_at"], pk: "rule_key", fk: {}, why: "Prices are data, not code: the admin changes them in the Prices panel. A ride keeps the price saved at booking." },
  driver_shifts: { desc: "When each driver was online", cols: ["shift_id", "driver_id", "started_at", "ended_at"], pk: "shift_id", fk: { driver_id: "DRIVERS" }, why: "A driver is online while their shift has no ended_at. Only online drivers get orders." },
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
    <label class="field"><span>email (used to log in)</span><input type="email" name="email" placeholder="name@taxi.kz" required></label>
    <label class="field"><span>license_number</span><input type="text" name="license_number" placeholder="AA 1234567" required></label>
    <label class="field"><span>rating (1–5)</span><input type="number" name="rating" min="1" max="5" step="0.1" value="5"></label>
    <label class="field"><span>password (min 6)</span><input type="password" name="password" minlength="6" autocomplete="new-password" required></label>`;
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
  const h = await api("/api/reports/driver-hours");
  const maxH = Math.max(1, ...h.rows.map(x => x.hours));
  $("#hours").innerHTML = `<h3>Hours online, last 7 days</h3><div class="muted" style="font-size:13px">From DRIVER_SHIFTS. An open shift counts until now.</div>
    <div class="bars">${h.rows.map(x => `<div class="bar-row">
      <div class="name">${esc(x.full_name)}<small>${x.shifts} shifts</small></div>
      <div class="bar-track"><div class="bar-fill" style="width:0" data-w="${(x.hours / maxH) * 100}%"></div></div>
      <div class="val">${x.hours} h</div></div>`).join("") || '<p class="muted">No shifts in the last 7 days</p>'}</div>`;
  requestAnimationFrame(() => $$("#hours .bar-fill").forEach(el => (el.style.width = el.dataset.w)));
}
$("#monthSelect").addEventListener("change", loadReports);

/* =========================== ADMIN: ACCESS & ROLES =========================== */
const MATRIX = [
  ["PASSENGERS", "Own profile; signs up (create)", "Name + phone of the current passenger only", "Read all, add"],
  ["DRIVERS", "Name, phone, rating of own assigned driver", "Own profile", "Read all, add"],
  ["CARS", "Model, color, plate of own assigned car", "Own cars", "Read all, add"],
  ["RIDES", "Own rides: create, cancel while active", "Own assigned rides: complete", "Read all, cancel"],
  ["FARE_RULES", "Read active prices", "Read active prices", "Read all, change prices, switch extras on/off"],
  ["DRIVER_SHIFTS", "No access", "Own shifts: go online / offline", "Read all, hours report"],
  ["PAYMENTS", "Own rides: pay again by card", "Own rides: create payment (cash/card)", "Read all, reports"],
];
const AREAS = [
  { t: "Systems Analysis & Requirements", r: "Users, problems, requirements, business rules", li: ["Main action: a passenger books a ride", "Roles: passenger, driver, admin", "A driver has only one active ride at a time", "A passenger has only one active ride at a time"] },
  { t: "Data & Database", r: "ERD, entities, relationships, SQL", li: ["5 tables: PASSENGERS, DRIVERS, CARS, RIDES, PAYMENTS", "PK, FK and CHECK constraints in schema.sql", "The Database tab shows the live tables"] },
  { t: "Application & Development", r: "Core functionality, business logic, UI", li: ["Flask API (app.py) + three role interfaces", "Prices come from the FARE_RULES table", "The admin changes them in the Prices panel", "The free driver with the best rating is assigned"] },
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
