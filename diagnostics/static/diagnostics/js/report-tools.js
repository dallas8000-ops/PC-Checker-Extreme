(function () {
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
