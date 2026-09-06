(function () {
  function readCsrf() {
    const input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  document.querySelectorAll(".btn-fix").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const fixId = btn.getAttribute("data-fix-id");
      const result = btn.parentElement.querySelector(".fix-result");
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = "Working…";
      if (result) result.textContent = "";

      fetch("/api/fix/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": readCsrf(),
        },
        body: JSON.stringify({ fix_id: fixId }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          const msg = data.message || data.error || "Done";
          if (result) {
            result.textContent = " " + msg;
            result.className = "fix-result " + (data.ok ? "fix-ok" : "fix-fail");
          }
          btn.textContent = data.ok ? "Done" : "Failed";
          if (!data.ok) btn.disabled = false;
        })
        .catch(function (err) {
          if (result) {
            result.textContent = " Request failed: " + err;
            result.className = "fix-result fix-fail";
          }
          btn.textContent = prev;
          btn.disabled = false;
        });
    });
  });

  document.querySelectorAll(".btn-copy-cmd").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const card = btn.closest(".playbook-card");
      const ta = card && card.querySelector(".playbook-cmd");
      if (!ta) return;
      navigator.clipboard.writeText(ta.value).then(function () {
        const prev = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(function () {
          btn.textContent = prev;
        }, 1500);
      });
    });
  });

  const chatForm = document.getElementById("scan-chat-form");
  const chatLog = document.getElementById("scan-chat-log");
  const chatInput = document.getElementById("scan-chat-input");
  if (!chatForm || !chatLog) return;

  function getCsrf() {
    const input = chatForm.querySelector("[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function appendMsg(role, text) {
    const div = document.createElement("div");
    div.className = "scan-chat-msg scan-chat-" + role;
    div.textContent = text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  chatForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const message = (chatInput.value || "").trim();
    if (!message) return;
    const url = chatForm.getAttribute("data-chat-url");
    appendMsg("user", message);
    chatInput.value = "";
    chatInput.disabled = true;

    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrf(),
      },
      body: JSON.stringify({ message: message }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        appendMsg("assistant", data.reply || data.error || "No response");
      })
      .catch(function (err) {
        appendMsg("assistant", "Request failed: " + err);
      })
      .finally(function () {
        chatInput.disabled = false;
        chatInput.focus();
      });
  });
})();
