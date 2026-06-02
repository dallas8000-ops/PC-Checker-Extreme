(function () {
  const id = window.PCC_SCAN_ID;
  if (!id) return;

  const fill = document.getElementById("progress-fill");
  const pct = document.getElementById("progress-pct");
  const stage = document.getElementById("progress-stage");

  function poll() {
    fetch("/api/scan/" + id + "/status/")
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        const p = data.progress || 0;
        if (fill) fill.style.width = p + "%";
        if (pct) pct.textContent = p;
        if (stage) stage.textContent = data.stage || data.status;

        if (data.status === "complete" && data.redirect) {
          window.location.href = data.redirect;
          return;
        }
        if (data.status === "failed") {
          if (data.error) stage.textContent = "Failed: " + data.error;
          setTimeout(function () {
            window.location.href = "/scan/" + id + "/";
          }, 2500);
          return;
        }
        setTimeout(poll, 1200);
      })
      .catch(function () {
        setTimeout(poll, 2000);
      });
  }

  poll();
})();
