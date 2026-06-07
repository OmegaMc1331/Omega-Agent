const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");

function appendMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  article.appendChild(bubble);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function setThinking(active) {
  let node = document.querySelector("#thinking");
  if (active && !node) {
    node = appendMessage("assistant", "Omega réfléchit...");
    node.id = "thinking";
  }
  if (!active && node) {
    node.remove();
  }
}

async function loadStatus() {
  const response = await fetch("/api/status");
  const status = await response.json();
  document.querySelector("#provider").textContent = status.provider || "inconnu";
  document.querySelector("#model").textContent = status.model || "inconnu";
  document.querySelector("#workspace").textContent = status.workspace || "inconnu";
  if (status.login_hint) {
    appendMessage("assistant warning", status.login_hint);
  }
}

async function sendMessage(text) {
  appendMessage("user", text);
  setThinking(true);
  sendButton.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const payload = await response.json();
    setThinking(false);
    appendMessage("assistant", payload.message || payload.detail || "Réponse vide.");
  } catch (error) {
    setThinking(false);
    appendMessage("assistant warning", "Erreur de connexion au gateway.");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

loadStatus();
