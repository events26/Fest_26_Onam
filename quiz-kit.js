/* Onotsavam Quiz — shared client: team palette, live state feed, sound. */

/* Eight hues that stay apart from each other across a hall. Several are drawn
   from the team's own referent — Pulikali's tiger yellow, Vallam's backwater
   teal — rather than assigned arbitrarily. `ink` is what stays readable on top. */
const TEAM_STYLE = {
  "Thiruvonam Titan's": { c:"#ff7a00", ink:"#2b1505" },
  "Gajaveerans":        { c:"#8b46f0", ink:"#ffffff" },
  "Pulikali Panthers":  { c:"#ffcc00", ink:"#2b1505" },
  "Onam Kombans":       { c:"#e3253f", ink:"#ffffff" },
  "Maveli Squad":       { c:"#12a05a", ink:"#ffffff" },
  "Chenda Champions":   { c:"#ec2a86", ink:"#ffffff" },
  "Vallam Vikings":     { c:"#12aecd", ink:"#2b1505" },
  "Kerala Vibes":       { c:"#86cc16", ink:"#2b1505" }
};
const FALLBACK = [
  { c:"#ff7a00", ink:"#2b1505" }, { c:"#8b46f0", ink:"#ffffff" },
  { c:"#ffcc00", ink:"#2b1505" }, { c:"#e3253f", ink:"#ffffff" },
  { c:"#12a05a", ink:"#ffffff" }, { c:"#ec2a86", ink:"#ffffff" },
  { c:"#12aecd", ink:"#2b1505" }, { c:"#86cc16", ink:"#2b1505" }
];

function teamStyle(name, index) {
  return TEAM_STYLE[name] || FALLBACK[(index || 0) % FALLBACK.length];
}

/* Short names for the scoreboard strip — full names won't fit eight across. */
function shortName(name) {
  const first = String(name || "").split(" ")[0];
  return first.length > 11 ? first.slice(0, 10) + "…" : first;
}

/* Scores carry halves and can go negative. Show 10 not 10.0, 7.5 not 7.50,
   and keep the sign on penalties so a rule reads as a rule. */
function pts(n) {
  const v = Math.round(Number(n) * 100) / 100;
  return Number.isInteger(v) ? String(v) : String(v);
}
function signed(n) {
  const v = Number(n);
  return (v > 0 ? "+" : "") + pts(v);
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => (
    { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]
  ));
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });
  return res.json().catch(() => ({ ok:false }));
}

/* Live state. EventSource reconnects on its own; we only surface the gap so
   nobody trusts a frozen screen. */
function connect(onState) {
  const flag = document.querySelector(".offline");
  let es;
  const open = () => {
    es = new EventSource("/events");
    es.onmessage = e => {
      if (flag) flag.classList.remove("show");
      try { onState(JSON.parse(e.data)); } catch (_) {}
    };
    es.onerror = () => { if (flag) flag.classList.add("show"); };
  };
  open();
  // A phone that slept can come back with a dead stream that never errors.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && es && es.readyState === 2) open();
  });
}

/* ------------------------------------------------------------------ sound --
   Synthesised, so there are no audio files to lose before the event. iOS
   keeps the context suspended until a real gesture, hence unlock(). */
const Sound = (() => {
  let ctx = null;
  const ac = () => (ctx = ctx || new (window.AudioContext || window.webkitAudioContext)());

  function unlock() { const c = ac(); if (c.state === "suspended") c.resume(); }

  /* Chenda-ish: a noise crack over a low body, both decaying fast. */
  function hit(vol) {
    const c = ac(), t = c.currentTime, v = vol == null ? 0.5 : vol;

    const n = c.createBuffer(1, c.sampleRate * 0.18, c.sampleRate);
    const d = n.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
    const src = c.createBufferSource(); src.buffer = n;
    const bp = c.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 1900; bp.Q.value = 0.8;
    const ng = c.createGain(); ng.gain.setValueAtTime(v * 0.5, t);
    ng.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
    src.connect(bp).connect(ng).connect(c.destination); src.start(t);

    const o = c.createOscillator(), og = c.createGain();
    o.type = "triangle";
    o.frequency.setValueAtTime(320, t); o.frequency.exponentialRampToValueAtTime(90, t + 0.15);
    og.gain.setValueAtTime(v, t); og.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
    o.connect(og).connect(c.destination); o.start(t); o.stop(t + 0.24);
  }

  /* Two rising notes — buzzers are open. */
  function arm() {
    const c = ac(), t = c.currentTime;
    [[523.25, 0], [784, 0.1]].forEach(([f, at]) => {
      const o = c.createOscillator(), g = c.createGain();
      o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0, t + at);
      g.gain.linearRampToValueAtTime(0.28, t + at + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, t + at + 0.3);
      o.connect(g).connect(c.destination); o.start(t + at); o.stop(t + at + 0.32);
    });
  }

  return { unlock, hit, arm };
})();
