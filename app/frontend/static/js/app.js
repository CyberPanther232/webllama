document.addEventListener("DOMContentLoaded", () => {
    if (window.lucide) {
        window.lucide.createIcons();
    }

    const chatForm = document.querySelector("[data-chat-form]");
    const chatInput = document.querySelector("[data-chat-input]");
    const conversation = document.querySelector("[data-conversation]");
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    const modelSelect = document.querySelector("[data-model-select]");

    const addMessage = (name, text, isUser) => {
        const message = document.createElement("article");
        message.className = `message${isUser ? " user" : ""}`;
        message.innerHTML = `<div class="avatar">${isUser ? "Y" : "W"}</div><div class="message-content"><strong>${name}</strong><span></span></div>`;
        message.querySelector("span").textContent = text;
        conversation.append(message);
        conversation.scrollTop = conversation.scrollHeight;
    };

    document.querySelectorAll("[data-prompt]").forEach((button) => {
        button.addEventListener("click", () => {
            chatInput.value = button.dataset.prompt;
            chatInput.focus();
        });
    });

    chatForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const prompt = chatInput.value.trim();
        if (!prompt) return;
        addMessage("You", prompt, true);
        chatInput.value = "";
        const sendButton = chatForm.querySelector("button[type='submit']");
        sendButton.disabled = true;
        const chatId = chatForm.dataset.chatId;
        if (chatId) {
            try {
                const response = await fetch(`/api/send-prompt/chat_id=${encodeURIComponent(chatId)}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
                    body: JSON.stringify({ prompt, model: modelSelect?.value }),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || "Could not send the prompt.");
                }
                document.querySelector("[data-chat-title]").textContent = result.title;
                addMessage(`Webllama · ${result.model}`, result.response);
            } catch (error) {
                addMessage("Webllama", error.message || "Could not send the prompt.");
            } finally {
                sendButton.disabled = false;
            }
        }
    });

    modelSelect?.addEventListener("change", async () => {
        if (!modelSelect.value) return;
        try {
            const response = await fetch("/api/models/selection", {
                method: "PUT",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
                body: JSON.stringify({ model: modelSelect.value }),
            });
            if (!response.ok) {
                throw new Error();
            }
            const deleteButton = document.querySelector("[data-delete-model]");
            if (deleteButton) {
                deleteButton.dataset.deleteModel = modelSelect.value;
                deleteButton.disabled = false;
            }
        } catch {
            window.alert("Could not save the selected model.");
        }
    });


    const testConnectionButton = document.querySelector("[data-test-connection]");
    const baseUrlInput = document.querySelector("[data-base-url]");
    const connectionState = document.querySelector("[data-connection-state]");
    const saveSettingsButton = document.querySelector("[data-save-settings]");
    const keepLocalInput = document.querySelector("[data-keep-local]");
    const streamResponsesInput = document.querySelector("[data-stream-responses]");
    const contextWindowInput = document.querySelector("[data-context-window]");
    const saveState = document.querySelector("[data-save-state]");
    const oauthProviderInput = document.querySelector("[data-oauth-provider]");
    const oauthPlatformField = document.querySelector("[data-oauth-platform-field]");
    const oauthPlatformNameInput = document.querySelector("[data-oauth-platform-name]");
    const oauthIssuerField = document.querySelector("[data-oauth-issuer-field]");
    const oauthIssuerUrlInput = document.querySelector("[data-oauth-issuer-url]");
    const oauthClientIdInput = document.querySelector("[data-oauth-client-id]");
    const oauthRedirectUriInput = document.querySelector("[data-oauth-redirect-uri]");
    const generateRedirectUriButton = document.querySelector("[data-generate-redirect-uri]");

    oauthProviderInput?.addEventListener("change", () => {
        oauthPlatformField.hidden = oauthProviderInput.value !== "custom";
        oauthIssuerField.hidden = oauthProviderInput.value !== "custom";
        if (oauthProviderInput.value !== "custom") {
            oauthPlatformNameInput.value = "";
            oauthIssuerUrlInput.value = "";
        }
    });

    generateRedirectUriButton?.addEventListener("click", () => {
        oauthRedirectUriInput.value = `${window.location.origin}/auth/callback`;
        oauthRedirectUriInput.focus();
    });

    testConnectionButton?.addEventListener("click", async () => {
        const baseUrl = baseUrlInput.value.trim();
        if (!baseUrl) return;
        testConnectionButton.disabled = true;
        connectionState.textContent = "Testing connection...";

        try {
            const response = await fetch("/api/test-connection", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
                body: JSON.stringify({ base_url: baseUrl }),
            });
            const result = await response.json();
            connectionState.textContent = response.ok
                ? `Connection successful (Ollama ${result.version})`
                : result.error || "Connection failed";
        } catch {
            connectionState.textContent = "Connection failed";
        } finally {
            testConnectionButton.disabled = false;
        }
    });

    saveSettingsButton?.addEventListener("click", async () => {
        saveSettingsButton.disabled = true;
        saveState.textContent = "Saving settings...";

        try {
            const response = await fetch("/api/settings", {
                method: "PUT",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
                body: JSON.stringify({
                    keep_conversations_local: keepLocalInput.checked,
                    stream_responses: streamResponsesInput.checked,
                    context_window_tokens: Number(contextWindowInput.value),
                    oauth_provider: oauthProviderInput?.value || "",
                    oauth_platform_name: oauthPlatformNameInput?.value.trim() || "",
                    oauth_issuer_url: oauthIssuerUrlInput?.value.trim() || "",
                    oauth_client_id: oauthClientIdInput?.value.trim() || "",
                    oauth_redirect_uri: oauthRedirectUriInput?.value.trim() || "",
                }),
            });
            const result = await response.json();
            saveState.textContent = response.ok ? result.message : result.error || "Could not save settings.";
        } catch {
            saveState.textContent = "Could not save settings.";
        } finally {
            saveSettingsButton.disabled = false;
        }
    });

    const pullModelForm = document.querySelector("[data-pull-model-form]");
    const pullModelInput = document.querySelector("[data-pull-model]");
    const modelState = document.querySelector("[data-model-state]");

    pullModelForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const model = pullModelInput.value.trim();
        if (!model) return;
        const submitButton = pullModelForm.querySelector("button[type='submit']");
        submitButton.disabled = true;
        modelState.textContent = `Pulling ${model}...`;
        try {
            const response = await fetch("/api/models/pull", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
                body: JSON.stringify({ model }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            window.location.reload();
        } catch (error) {
            modelState.textContent = error.message || "Could not pull the model.";
            submitButton.disabled = false;
        }
    });

    document.querySelectorAll("[data-delete-model]").forEach((button) => {
        button.addEventListener("click", async () => {
            const model = button.dataset.deleteModel;
            if (!window.confirm(`Delete ${model} from this host?`)) return;
            button.disabled = true;
            if (modelState) modelState.textContent = `Removing ${model}...`;
            try {
                const response = await fetch(`/api/models/${encodeURIComponent(model)}`, {
                    method: "DELETE",
                    headers: { "X-CSRF-Token": csrfToken },
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error);
                window.location.reload();
            } catch (error) {
                if (modelState) modelState.textContent = error.message || "Could not remove the model.";
                button.disabled = false;
            }
        });
    });

});