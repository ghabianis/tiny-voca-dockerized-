const textInput = document.querySelector("#text");
const voiceInputs = document.querySelectorAll('input[name="voice"]');
const speakButton = document.querySelector("#speak");
const buttonLabel = document.querySelector("#button-label");
const message = document.querySelector("#message");
const count = document.querySelector("#character-count");
const result = document.querySelector("#result");
const audio = document.querySelector("#audio");
const download = document.querySelector("#download");
const serverStatus = document.querySelector(".server-status");
let ready = false;
let busy = false;
let audioUrl = null;

function update() {
  count.textContent = `${textInput.value.length.toLocaleString()} / 2,000`;
  speakButton.disabled = !ready || busy || !textInput.value.trim();
}

function setMessage(value, isError = false) {
  message.textContent = value;
  message.classList.toggle("error", isError);
}

async function checkReady() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("The speech service is not ready.");
    await response.json();
    ready = true;
    serverStatus.classList.add("ready");
    serverStatus.querySelector("span").textContent = "Model ready";
    setMessage("Ready when you are.");
  } catch (error) {
    ready = false;
    serverStatus.classList.add("error");
    serverStatus.querySelector("span").textContent = "Model unavailable";
    setMessage(error.message, true);
  }
  update();
}

for (const button of document.querySelectorAll("[data-example]")) {
  button.addEventListener("click", () => {
    textInput.value = button.dataset.example;
    update();
    textInput.focus();
  });
}

textInput.addEventListener("input", update);

speakButton.addEventListener("click", async () => {
  if (!ready || busy) return;
  busy = true;
  speakButton.classList.add("loading");
  buttonLabel.textContent = "Generating…";
  setMessage("Generating speech with the model on this server. Longer text may take a little while.");
  update();

  try {
    const voice = document.querySelector('input[name="voice"]:checked').value;
    const response = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: textInput.value, voice }),
    });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.error || "Speech generation failed.");
    }

    const blob = await response.blob();
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = URL.createObjectURL(blob);
    audio.src = audioUrl;
    download.href = audioUrl;
    result.hidden = false;
    setMessage("Your audio is ready.");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    busy = false;
    speakButton.classList.remove("loading");
    buttonLabel.textContent = "Generate speech";
    update();
  }
});

update();
checkReady();
