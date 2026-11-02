import { SUPABASE_URL, SUPABASE_ANON_KEY, TABLE, BUCKET, MAX_POINTS, IMAGE_POLL_MS } from "./config.js";

const DEMO = !SUPABASE_URL || !SUPABASE_ANON_KEY;
let supabase = null; // will be initialized in live mode

// ---- element references
const $ = (id) => document.getElementById(id);
const el = {
  sog: $("sog"),
  cog: $("cog"),
  position: $("position"),
  geotag: $("geotag"),
  score: $("score"),
  surface: $("cam-surface"),
  status: $("status"),
  statusText: $("status-text"),
};

function setStatus(kind, text) {
  el.status.className = "status " + kind;
  el.statusText.textContent = text;
}

// ---- chart (line, axes 0..25)
const chart = new Chart($("realtimePlot"), {
  type: "line",
  data: {
    datasets: [{
      label: "Lintasan",
      data: [],
      showLine: true,
      borderColor: "#2A8FC4", // mid blue for light theme
      borderWidth: 2,
      pointRadius: 2,
      pointBackgroundColor: "#2A8FC4",
      tension: 0.2,
    }]
  },
  options: {
    animation: false,
    maintainAspectRatio: false,
    parsing: false,
    scales: {
      x: { type: "linear", min: 0, max: 25, ticks: { color: "#0E4A75", stepSize: 5 }, grid: { color: "#2A8FC4" } },
      y: { type: "linear", min: 0, max: 25, ticks: { color: "#0E4A75", stepSize: 5 }, grid: { color: "#2A8FC4" } },
    },
    plugins: { legend: { display: false } },
  },
});

// ---- dashboard update
function updateDashboard(data) {
  if (!data) return;
  if (data.sog != null) el.sog.textContent = `${Number(data.sog).toFixed(1)} Knot`;
  if (data.cog != null) el.cog.textContent = `${Math.round(data.cog)}°`;
  if (data.position) el.position.textContent = data.position;
  if (data.geotag) el.geotag.textContent = data.geotag;
  if (data.score != null) el.score.textContent = data.score;

  if (data.x != null && data.y != null) {
    const pts = chart.data.datasets[0].data;
    pts.push({ x: Number(data.x), y: Number(data.y) });
    if (pts.length > MAX_POINTS) pts.shift();
    chart.update();
  }
}

// ---- image handling (surface only)
const pick = (files, words) => files.find((f) => words.some((w) => f.name.toLowerCase().includes(w)));

async function updateImages() {
  if (!supabase) return; // safety for demo mode
  const { data: files, error } = await supabase.storage.from(BUCKET)
    .list("", { limit: 10, sortBy: { column: "created_at", order: "desc" } });
  if (error) { console.error("Gagal cek gambar:", error.message); return; }
  if (!files || !files.length) { console.warn("Bucket kosong"); return; }

  const bust = Date.now(); // anti‑cache
  const surface = pick(files, ["green", "surface"]);
  if (surface) {
    const url = supabase.storage.from(BUCKET).getPublicUrl(surface.name).data.publicUrl;
    const next = `${url}?t=${bust}`;
    if (el.surface.dataset.file !== surface.name) {
      el.surface.dataset.file = surface.name;
      el.surface.src = next;
    }
  }
}

// ---- modal (surface only)
const modal = document.createElement("div");
modal.className = "modal";
modal.innerHTML = '<button class="close" aria-label="Tutup">&times;</button><img alt=""><div class="caption"></div>';
document.body.appendChild(modal);
const modalImg = modal.querySelector("img");
const caption = modal.querySelector(".caption");
const closeModal = () => modal.classList.remove("show");
function openModal(img) { modalImg.src = img.src; caption.textContent = img.alt; modal.classList.add("show"); }
el.surface.addEventListener("click", () => openModal(el.surface));
modal.querySelector(".close").addEventListener("click", closeModal);
modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

// ---- live mode (Supabase)
async function startLive() {
  try {
    const { createClient } = await import("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm");
    supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  } catch (e) {
    setStatus("err", "Library gagal dimuat");
    console.error(e);
    return;
  }
  const { data, error } = await supabase.from(TABLE).select("*")
    .order("created_at", { ascending: false }).limit(1);
  if (error) { setStatus("err", "Gagal ambil data"); console.error(error.message); }
  else if (data && data.length) updateDashboard(data[0]);

  supabase.channel("realtime-mission")
    .on("postgres_changes", { event: "INSERT", schema: "public", table: TABLE }, (payload) => {
      console.log("Data baru:", payload.new);
      updateDashboard(payload.new);
    })
    .subscribe((s) => {
      if (s === "SUBSCRIBED") setStatus("live", "Live");
      else if (s === "CHANNEL_ERROR" || s === "TIMED_OUT") setStatus("err", "Terputus");
    });

  updateImages();
  setInterval(updateImages, IMAGE_POLL_MS);
}

// ---- demo mode (no Supabase)
function startDemo() {
  setStatus("", "Mode DEMO");
  let t = 0, score = 0;
  setInterval(() => {
    t += 0.1;
    const x = 12.5 + 8.75 * Math.cos(t), y = 12.5 + 8.75 * Math.sin(t);
    if (Math.floor(t * 10) % 40 === 0) score += 10;
    const col = String.fromCharCode(65 + Math.min(4, Math.floor(x / 5)));
    updateDashboard({
      sog: 1.2 + 0.3 * Math.sin(t),
      cog: (Math.atan2(Math.cos(t), -Math.sin(t)) * 180 / Math.PI + 360) % 360,
      position: `${col}${Math.min(5, Math.floor(y / 5) + 1)}`,
      geotag: new Date().toLocaleString("id-ID") + ", -7.952100, 112.614500",
      score,
      x,
      y,
    });
  }, 500);
}

DEMO ? startDemo() : startLive();