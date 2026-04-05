(function () {
  const state = {
    source: null,
    running: false,
    sawError: false,
  };

  function createFab() {
    const fab = document.createElement("button");
    fab.id = "ops-fab";
    fab.type = "button";
    fab.setAttribute("aria-label", "Open Obsidian Ops");
    fab.textContent = "*";
    document.body.appendChild(fab);
    return fab;
  }

  function createModal() {
    const backdrop = document.createElement("div");
    backdrop.id = "ops-modal-backdrop";
    backdrop.innerHTML = `
      <div id="ops-modal" role="dialog" aria-modal="true" aria-label="Obsidian Ops">
        <div id="ops-modal-header">
          <p id="ops-page-context"></p>
          <button id="ops-close" type="button" aria-label="Close">x</button>
        </div>
        <textarea id="ops-instruction" rows="4" placeholder="Describe what to do with this note..."></textarea>
        <button id="ops-submit" type="button">Run</button>
        <div id="ops-summary"></div>
        <div id="ops-progress"></div>
        <div id="ops-actions">
          <button id="ops-refresh" type="button">Refresh</button>
          <button id="ops-undo" type="button">Undo</button>
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);
    return backdrop;
  }

  function getEls() {
    return {
      backdrop: document.getElementById("ops-modal-backdrop"),
      modal: document.getElementById("ops-modal"),
      context: document.getElementById("ops-page-context"),
      close: document.getElementById("ops-close"),
      input: document.getElementById("ops-instruction"),
      submit: document.getElementById("ops-submit"),
      summary: document.getElementById("ops-summary"),
      progress: document.getElementById("ops-progress"),
      refresh: document.getElementById("ops-refresh"),
      undo: document.getElementById("ops-undo"),
      actions: document.getElementById("ops-actions"),
    };
  }

  function resetState() {
    const els = getEls();
    els.modal.classList.remove("ops-running", "ops-success", "ops-error");
    els.submit.disabled = false;
    els.input.disabled = false;
    els.summary.textContent = "";
    els.progress.textContent = "";
    state.sawError = false;
  }

  function setRunningState() {
    const els = getEls();
    els.modal.classList.remove("ops-success", "ops-error");
    els.modal.classList.add("ops-running");
    els.submit.disabled = true;
    els.input.disabled = true;
    state.running = true;
    state.sawError = false;
  }

  function setSuccessState(summary) {
    const els = getEls();
    els.modal.classList.remove("ops-running", "ops-error");
    els.modal.classList.add("ops-success");
    els.submit.disabled = false;
    els.input.disabled = false;
    els.summary.textContent = summary || "Done.";
    state.running = false;
  }

  function setErrorState(message) {
    const els = getEls();
    els.modal.classList.remove("ops-running", "ops-success");
    els.modal.classList.add("ops-error");
    els.submit.disabled = false;
    els.input.disabled = false;
    els.summary.textContent = message || "Something went wrong.";
    state.running = false;
    state.sawError = true;
  }

  function appendProgress(line) {
    if (!line) {
      return;
    }
    const els = getEls();
    const next = els.progress.textContent ? `\n${line}` : line;
    els.progress.textContent += next;
    els.progress.scrollTop = els.progress.scrollHeight;
  }

  function openModal() {
    const els = getEls();
    resetState();
    els.context.textContent = `Current page: ${window.location.pathname}`;
    els.backdrop.classList.add("ops-open");
    els.input.focus();
  }

  function closeModal() {
    if (state.running) {
      const ok = window.confirm("A job is still running. Close this panel anyway?");
      if (!ok) {
        return;
      }
    }
    const els = getEls();
    els.backdrop.classList.remove("ops-open");
    resetState();
  }

  function closeSource() {
    if (state.source) {
      state.source.close();
      state.source = null;
    }
  }

  function parseEventData(event) {
    try {
      return JSON.parse(event.data);
    } catch (_error) {
      return { message: event.data || "" };
    }
  }

  function openSse(jobId) {
    closeSource();
    const source = new EventSource(`/api/jobs/${jobId}/stream`);
    state.source = source;

    source.addEventListener("status", (event) => {
      const payload = parseEventData(event);
      appendProgress(payload.message || "status");
    });

    source.addEventListener("tool", (event) => {
      const payload = parseEventData(event);
      appendProgress(payload.message || "tool call");
    });

    source.addEventListener("result", (event) => {
      const payload = parseEventData(event);
      if (payload.message) {
        appendProgress(payload.message);
      }
    });

    source.addEventListener("error", (event) => {
      const payload = parseEventData(event);
      appendProgress(payload.message || "Error");
      setErrorState(payload.message || "Job failed.");
    });

    source.addEventListener("done", (event) => {
      const payload = parseEventData(event);
      closeSource();
      if (state.sawError) {
        return;
      }
      setSuccessState(payload.message || "Done.");
    });

    source.onerror = () => {
      if (state.running) {
        appendProgress("Stream connection interrupted.");
      }
    };
  }

  async function submitJob() {
    const els = getEls();
    const instruction = els.input.value.trim();
    if (!instruction) {
      return;
    }

    setRunningState();
    appendProgress("Submitting job...");

    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction,
          current_url_path: window.location.pathname,
        }),
      });

      if (!response.ok) {
        throw new Error(`Job request failed (${response.status})`);
      }

      const payload = await response.json();
      appendProgress(`Job queued: ${payload.job_id}`);
      openSse(payload.job_id);
    } catch (error) {
      setErrorState(String(error));
    }
  }

  async function undoLastChange() {
    setRunningState();
    appendProgress("Submitting undo job...");

    try {
      const response = await fetch("/api/undo", {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error(`Undo request failed (${response.status})`);
      }

      const payload = await response.json();
      appendProgress(`Undo job queued: ${payload.job_id}`);
      openSse(payload.job_id);
    } catch (error) {
      setErrorState(String(error));
    }
  }

  function bindEvents() {
    const fab = document.getElementById("ops-fab") || createFab();
    const backdrop = document.getElementById("ops-modal-backdrop") || createModal();

    const els = getEls();
    fab.addEventListener("click", openModal);
    els.close.addEventListener("click", closeModal);
    els.submit.addEventListener("click", submitJob);
    els.refresh.addEventListener("click", () => window.location.reload());
    els.undo.addEventListener("click", undoLastChange);

    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) {
        closeModal();
      }
    });
  }

  function init() {
    if (document.getElementById("ops-fab") && document.getElementById("ops-modal-backdrop")) {
      return;
    }
    bindEvents();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
