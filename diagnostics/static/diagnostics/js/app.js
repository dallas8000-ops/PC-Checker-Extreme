(function () {
  const scanForm = document.getElementById("scan-form");
  if (scanForm) {
    const stages = [
      "Reading hardware (WMI)…",
      "Checking memory & disks…",
      "Listing installed software…",
      "Running health checks…",
      "AI analysis…",
      "Still working — winget/update checks can take several minutes…",
    ];
    let stageTimer = null;

    function setScanningUi() {
      const btn = document.getElementById("scan-btn");
      const headerBtn = document.getElementById("initiate-scan-btn");
      const statusEl = document.getElementById("scan-status");
      const slowChecks = scanForm.querySelector('[name="include_slow_checks"]')?.checked;

      if (btn) {
        btn.disabled = true;
        const label = btn.querySelector(".btn-label");
        const spinner = btn.querySelector(".btn-spinner");
        if (label) label.textContent = "▶ SCAN IN PROGRESS…";
        if (spinner) spinner.classList.remove("hidden");
      }
      if (headerBtn) {
        headerBtn.disabled = true;
        headerBtn.textContent = "SCANNING…";
      }

      return { statusEl, slowChecks };
    }

    scanForm.addEventListener("submit", function () {
      const { statusEl, slowChecks } = setScanningUi();

      let i = 0;
      if (statusEl) {
        statusEl.textContent = stages[0];
        clearInterval(stageTimer);
        stageTimer = setInterval(function () {
          i = Math.min(i + 1, stages.length - 1);
          if (slowChecks && i >= 3) i = stages.length - 1;
          statusEl.textContent = stages[i];
        }, slowChecks ? 12000 : 8000);
      }
    });
  }

  document.querySelectorAll(".tab-nav .tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      const target = tab.dataset.tab;
      document.querySelectorAll(".tab-nav .tab").forEach(function (t) {
        t.classList.toggle("active", t === tab);
      });
      document.querySelectorAll(".tab-panel").forEach(function (panel) {
        panel.classList.toggle("active", panel.id === "tab-" + target);
      });
    });
  });

  document.querySelectorAll(".collapse-trigger").forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      const expanded = trigger.getAttribute("aria-expanded") === "true";
      trigger.setAttribute("aria-expanded", String(!expanded));
      const content = trigger.parentElement.querySelector(".collapse-content");
      if (content) content.style.display = expanded ? "none" : "block";
    });
  });

  const themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    const saved = localStorage.getItem("pcc-theme");
    if (saved === "light") document.body.classList.add("theme-light");
    themeBtn.addEventListener("click", function () {
      document.body.classList.toggle("theme-light");
      localStorage.setItem(
        "pcc-theme",
        document.body.classList.contains("theme-light") ? "light" : "dark"
      );
    });
  }

  const driverFilter = document.querySelector("[data-driver-filter]");
  if (driverFilter) {
    driverFilter.addEventListener("input", function () {
      const q = driverFilter.value.toLowerCase();
      document.querySelectorAll(".driver-row").forEach(function (row) {
        const name = row.getAttribute("data-name") || "";
        row.style.display = !q || name.indexOf(q) >= 0 ? "" : "none";
      });
    });
  }

  const copyWinget = document.getElementById("copy-winget");
  if (copyWinget) {
    copyWinget.addEventListener("click", function () {
      const ta = document.getElementById("winget-cmd");
      if (!ta) return;
      ta.select();
      navigator.clipboard.writeText(ta.value).then(function () {
        copyWinget.textContent = "Copied!";
      });
    });
  }

  document.querySelectorAll(".interactive-toggle").forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      const body = toggle.parentElement.querySelector(".interactive-body");
      const chevron = toggle.querySelector(".chevron");
      if (body) body.classList.toggle("hidden", expanded);
      if (chevron) chevron.textContent = expanded ? "+" : "−";
    });
  });
})();
