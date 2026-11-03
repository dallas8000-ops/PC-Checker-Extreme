(function () {
  const output = document.getElementById("tool-output");
  if (!output) return;
  const titleEl = document.getElementById("tool-output-title");
  const messageEl = document.getElementById("tool-output-message");
  const textEl = document.getElementById("tool-output-text");

  function readCsrf() {
    const input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function show(title, message, text, isError) {
    titleEl.textContent = title;
    messageEl.textContent = message || "";
    messageEl.classList.toggle("error", !!isError);
    textEl.textContent = text || "";
    textEl.classList.toggle("hidden", !text);
    output.classList.remove("hidden");
  }

  document.getElementById("tool-output-close").addEventListener("click", function () {
    output.classList.add("hidden");
  });

  document.querySelectorAll(".btn-tool").forEach(function (button) {
    button.addEventListener("click", async function () {
      const toolId = button.getAttribute("data-tool-id");
      const confirmText = button.getAttribute("data-confirm");
      const title = button.textContent.replace("ADMIN", "").trim();
      if (confirmText && !window.confirm(title + "\n\n" + confirmText + "\n\nContinue?")) return;

      document.querySelectorAll(".btn-tool").forEach(function (b) {
        b.disabled = true;
      });
      show(title, "Running… approve the Windows administrator prompt if one appears. Scans can take several minutes.", "", false);

      try {
        const response = await fetch("/api/tools/run/", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CSRFToken": readCsrf(),
          },
          body: JSON.stringify({ tool_id: toolId }),
        });
        const data = await response.json().catch(function () {
          return {};
        });
        if (data.reload) {
          show(title, data.error, "", true);
          window.setTimeout(function () {
            window.location.reload();
          }, 2000);
          return;
        }
        const message = data.message || data.error || (response.ok ? "Done." : "Tool failed.");
        const suffix = data.reboot_required ? " Restart your PC to finish." : "";
        show(title, message + suffix, data.output || "", !response.ok);
      } catch (error) {
        show(title, "Request failed: " + error, "", true);
      } finally {
        document.querySelectorAll(".btn-tool").forEach(function (b) {
          b.disabled = false;
        });
      }
    });
  });
})();
