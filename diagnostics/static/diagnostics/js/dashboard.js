(function () {
  if (typeof Chart === "undefined") return;

  const data = window.PCC_DASHBOARD || {};
  const cpu = data.cpu ?? 35;
  const ram = data.ram ?? 48;
  const disk = data.disk ?? 62;
  const ringScore = data.ringScore ?? Math.round((100 - (cpu + ram + disk) / 3));
  const history = data.history?.length ? data.history : [65, 72, 78, 81, 85];

  Chart.defaults.color = "#6b7a99";
  Chart.defaults.borderColor = "rgba(0, 240, 255, 0.08)";
  Chart.defaults.font.family = "'Rajdhani', sans-serif";

  const gridColor = "rgba(0, 240, 255, 0.06)";

  const ringEl = document.getElementById("chart-health-ring");
  if (ringEl) {
    const remainder = Math.max(0, 100 - ringScore);
    new Chart(ringEl, {
      type: "doughnut",
      data: {
        labels: ["Health", "Gap"],
        datasets: [
          {
            data: [ringScore, remainder],
            backgroundColor: [
              "rgba(255, 45, 154, 0.85)",
              "rgba(0, 240, 255, 0.08)",
            ],
            borderWidth: 0,
            hoverOffset: 4,
          },
          {
            data: [ringScore * 0.7, 100 - ringScore * 0.7],
            backgroundColor: [
              "rgba(0, 240, 255, 0.35)",
              "transparent",
            ],
            borderWidth: 0,
          },
        ],
      },
      options: {
        cutout: "72%",
        responsive: true,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
      },
    });
    const ringVal = document.getElementById("ring-score");
    if (ringVal && ringVal.textContent === "—") ringVal.textContent = ringScore;
  }

  const histEl = document.getElementById("chart-history");
  if (histEl) {
    new Chart(histEl, {
      type: "line",
      data: {
        labels: history.map((_, i) => `T-${history.length - i}`),
        datasets: [
          {
            label: "Health",
            data: history,
            borderColor: "#ff2d9a",
            backgroundColor: "rgba(255, 45, 154, 0.15)",
            fill: true,
            tension: 0.4,
            pointRadius: 3,
            pointBackgroundColor: "#00f0ff",
          },
          {
            label: "CPU est.",
            data: history.map((h) => Math.min(99, 100 - h + 15)),
            borderColor: "rgba(0, 240, 255, 0.5)",
            backgroundColor: "rgba(0, 240, 255, 0.05)",
            fill: true,
            tension: 0.4,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          x: { grid: { color: gridColor } },
          y: { min: 0, max: 100, grid: { color: gridColor } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  const waveEl = document.getElementById("chart-waveform");
  if (waveEl) {
    const pts = Array.from({ length: 40 }, (_, i) => {
      const t = i / 40;
      return 50 + Math.sin(t * Math.PI * 4) * 25 + (cpu / 100) * 15 * Math.cos(t * 8);
    });
    new Chart(waveEl, {
      type: "line",
      data: {
        labels: pts.map((_, i) => i),
        datasets: [
          {
            data: pts,
            borderColor: "#00f0ff",
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.35,
          },
          {
            data: pts.map((v) => 100 - v),
            borderColor: "rgba(255, 45, 154, 0.6)",
            borderWidth: 1,
            pointRadius: 0,
            tension: 0.35,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          x: { display: false },
          y: { display: false, min: 0, max: 100 },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  const modEl = document.getElementById("chart-modules");
  if (modEl) {
    new Chart(modEl, {
      type: "bar",
      data: {
        labels: ["CPU", "GPU", "RAM", "SSD", "NET", "SW"],
        datasets: [
          {
            data: [95, 88, 92, 85, 78, 70],
            backgroundColor: [
              "rgba(0, 240, 255, 0.7)",
              "rgba(255, 45, 154, 0.7)",
              "rgba(0, 240, 255, 0.5)",
              "rgba(178, 77, 255, 0.7)",
              "rgba(255, 45, 154, 0.5)",
              "rgba(178, 77, 255, 0.5)",
            ],
            borderRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          x: { grid: { display: false } },
          y: { display: false, max: 100 },
        },
        plugins: { legend: { display: false } },
      },
    });
  }
})();
