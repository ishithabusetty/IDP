const STAGES = {
  Normal: {
    key: "Normal",
    title: "1. NORMAL (NORM)",
    subtitle: "No Fall Detected",
    percent: 0,
    tone: "green",
    caption: "System in normal state. Airbag is completely deflated.",
  },
  Freefall: {
    key: "Freefall",
    title: "2. FALL DETECTED (ALRM)",
    subtitle: "Fall Detected",
    percent: 20,
    tone: "yellow",
    caption: "Fall detected. Airbag partially inflates (around 20%) to prepare for impact.",
  },
  Impact: {
    key: "Impact",
    title: "3. IMPACT (IMPT)",
    subtitle: "Impact Detected",
    percent: 80,
    tone: "orange",
    caption: "Impact detected. Airbag inflates further (around 80%) to absorb the shock.",
  },
  Deploy: {
    key: "Deploy",
    title: "4. SOS TRIGGERED (SOS)",
    subtitle: "SOS Triggered",
    percent: 100,
    tone: "red",
    caption: "SOS triggered. Airbag fully deployed (100%) for maximum protection.",
  },
};

const TONE_CLASS = {
  green: "tone-green",
  yellow: "tone-yellow",
  orange: "tone-orange",
  red: "tone-red",
};

const defaultViz = {
  stage: "Normal",
  visualStage: "Normal",
  mode: "NORMAL",
  connected: false,
  simulationEnabled: true,
  magnitude: 0,
  gyroMagnitude: 0,
  pitch: 0,
  battery: 0,
};

function normalizeStage(viz) {
  const mode = String(viz?.mode || "").toUpperCase();
  if (mode === "SOS SENT" || mode === "PRE ALARM") return "Deploy";
  if (mode === "IMPACT") return "Impact";
  if (mode === "FREEFALL") return "Freefall";
  if (mode === "NORMAL") return "Normal";

  const explicit = String(viz?.visualStage || "").trim();
  if (explicit && explicit in STAGES) return explicit;

  const stage = String(viz?.stage || "").toUpperCase();
  if (stage.includes("SOS")) return "Deploy";
  if (stage.includes("IMPACT")) return "Impact";
  if (stage.includes("FALL") || stage.includes("FREEFALL") || stage.includes("PRE ALARM") || stage === "DROP" || stage === "ALRM") return "Freefall";
  if (stage.includes("NORMAL") || stage === "NORM") return "Normal";
  return "Normal";
}

function readVizState() {
  const node = document.getElementById("airbag-viz-state");
  if (node?.dataset) {
    return {
      stage: node.dataset.stage || defaultViz.stage,
      visualStage: node.dataset.visualStage || defaultViz.visualStage,
      mode: node.dataset.mode || defaultViz.mode,
      connected: node.dataset.connected === "true",
      simulationEnabled: node.dataset.simulationEnabled !== "false",
      magnitude: Number(node.dataset.magnitude || 0),
      gyroMagnitude: Number(node.dataset.gyroMagnitude || 0),
      pitch: Number(node.dataset.pitch || 0),
      battery: Number(node.dataset.battery || 0),
    };
  }

  return window.__fallGuardVizState || defaultViz;
}

function buildPanelMarkup() {
  const chipOrder = ["Normal", "Freefall", "Impact", "Deploy"];
  const chips = chipOrder
    .map((stage) => {
      const meta = STAGES[stage];
      return `
        <div class="airbag-stage-chip ${TONE_CLASS[meta.tone]}" data-stage="${stage}">
          <div class="stage-title">${meta.title}</div>
          <div class="stage-subtitle">${meta.subtitle}</div>
          <div class="stage-pill">Airbag: ${meta.percent}%</div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="airbag-panel" data-mode="offline">
      <div class="airbag-panel-header">AIRBAG DEPLOYMENT - STATE BASED ANIMATION</div>
      <div class="airbag-stage-strip">${chips}</div>
      <div class="airbag-stage-view" id="airbag-stage-view" data-stage="Normal" data-mode="offline" data-label="Airbag: 0%">
        <div class="airbag-grid"></div>
        <div class="airbag-stage-figure">
          <div class="airbag-stage-person">
            <div class="airbag-head"></div>
            <div class="airbag-body"></div>
            <div class="airbag-arm left"></div>
            <div class="airbag-arm right"></div>
            <div class="airbag-leg left"></div>
            <div class="airbag-leg right"></div>
            <div class="airbag-shell">
              <div class="airbag-layer top"></div>
              <div class="airbag-layer left-top"></div>
              <div class="airbag-layer right-top"></div>
              <div class="airbag-layer left-mid"></div>
              <div class="airbag-layer right-mid"></div>
              <div class="airbag-layer bottom"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="airbag-stage-caption" id="airbag-stage-caption"><strong>Normal.</strong> System in normal state. Airbag is completely deflated.</div>
    </div>
  `;
}

function mountAirbagPanel() {
  const host = document.getElementById("airbag-visual-host");
  if (!host) {
    window.requestAnimationFrame(mountAirbagPanel);
    return;
  }

  if (host.dataset.mounted === "1") {
    return;
  }

  host.dataset.mounted = "1";
  host.innerHTML = buildPanelMarkup();

  const panel = host.querySelector(".airbag-panel");
  const stageView = host.querySelector("#airbag-stage-view");
  const stageCaption = host.querySelector("#airbag-stage-caption");
  const chips = Array.from(host.querySelectorAll(".airbag-stage-chip"));

  let renderedProgress = 0;
  let rafId = 0;

  function syncDataset(progress, meta, connected) {
    panel.dataset.mode = connected ? "connected" : "offline";
    stageView.dataset.stage = meta.key;
    stageView.dataset.mode = connected ? "connected" : "offline";
    stageView.dataset.label = `Airbag: ${meta.percent}%`;
    stageView.style.setProperty("--bag-progress", String(progress));
    stageView.style.setProperty("--bag-scale", String(progress));
    stageView.style.setProperty("--bag-opacity", String(progress));
    chips.forEach((chip) => chip.classList.toggle("is-active", chip.dataset.stage === meta.key));
    stageCaption.innerHTML = `<strong>${meta.subtitle}.</strong> ${meta.caption}`;
  }

  function render(viz) {
    const stage = normalizeStage(viz);
    const meta = STAGES[stage] || STAGES.Normal;
    const connected = Boolean(viz.connected);
    const targetProgress = meta.percent / 100;

    if (!connected) {
      renderedProgress = targetProgress;
      syncDataset(renderedProgress, meta, connected);
      return;
    }

    const step = () => {
      const diff = targetProgress - renderedProgress;
      renderedProgress += diff * 0.08;
      if (Math.abs(diff) < 0.003) {
        renderedProgress = targetProgress;
      }
      syncDataset(renderedProgress, meta, connected);
      if (renderedProgress !== targetProgress) {
        rafId = window.requestAnimationFrame(step);
      }
    };

    window.cancelAnimationFrame(rafId);
    step();
  }

  function sync() {
    render(readVizState());
  }

  const onState = () => sync();
  window.addEventListener("fallguard-viz-state", onState);
  const pollTimer = window.setInterval(sync, 250);
  sync();

  window.addEventListener("beforeunload", () => {
    window.removeEventListener("fallguard-viz-state", onState);
    window.clearInterval(pollTimer);
    window.cancelAnimationFrame(rafId);
  });
}

mountAirbagPanel();
