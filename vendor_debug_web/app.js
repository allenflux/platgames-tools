"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("generate-form");
  const urlInput = $("game-url");
  const vendorSelect = $("vendor-select");
  const validitySelect = $("validity");
  const generateButton = $("generate-button");
  const resultCard = document.querySelector(".result-card");
  const message = $("form-message");
  let vendors = [];
  let requestId = 0;
  let controller = null;
  let result = null;
  let toastTimer = null;

  function selectedTool() {
    return vendors.find((vendor) => vendor.id === vendorSelect.value)?.tools?.find(
      (tool) => tool.id === "natural-free-token"
    );
  }

  function setLoading(loading) {
    form.setAttribute("aria-busy", String(loading));
    resultCard.setAttribute("aria-busy", String(loading));
    generateButton.disabled = loading || !selectedTool();
    $("generate-label").textContent = loading ? "正在生成…" : "生成调试链接";
    generateButton.querySelector(".button-spinner").hidden = !loading;
    generateButton.querySelector(".button-arrow").hidden = loading;
  }

  function hideMessage() {
    message.hidden = true;
    message.textContent = "";
    urlInput.removeAttribute("aria-invalid");
  }

  function showMessage(text, isError = false) {
    message.textContent = text;
    message.className = isError ? "message message-error" : "message";
    message.hidden = false;
  }

  function resetResult() {
    requestId += 1;
    controller?.abort();
    controller = null;
    result = null;
    resultCard.classList.remove("is-ready");
    $("result-content").hidden = true;
    $("result-empty").hidden = false;
    $("result-badge").hidden = true;
    $("result-url").value = "";
    $("result-token").value = "";
    $("result-meta").textContent = "";
    $("open-game").removeAttribute("href");
    $("toast").hidden = true;
    clearTimeout(toastTimer);
    hideMessage();
    setLoading(false);
  }

  async function readResponse(response) {
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("服务返回了无法识别的结果，请稍后重试。");
    }
    if (!response.ok) {
      throw new Error(typeof data.error === "string" ? data.error : "生成失败，请检查游戏链接后重试。");
    }
    return data;
  }

  function updateVendor() {
    resetResult();
    const vendor = vendors.find((item) => item.id === vendorSelect.value);
    const name = vendor?.name || "Panda";
    $("breadcrumb-vendor").textContent = name;
    $("vendor-badge").textContent = name;
    document.title = `${name} · 游戏调试工具`;
    if (!selectedTool()) {
      showMessage("该厂商暂未提供自然免费调试工具。", true);
    }
  }

  async function loadVendors() {
    vendorSelect.disabled = true;
    generateButton.disabled = true;
    $("retry-catalog").disabled = true;
    $("catalog-error").hidden = true;
    document.querySelector(".service-status").classList.add("is-pending");
    $("service-status-text").textContent = "正在连接调试服务";
    try {
      const data = await readResponse(await fetch("/api/vendors", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      }));
      if (!Array.isArray(data.vendors) || !data.vendors.length) {
        throw new Error("暂时没有可用的厂商工具。");
      }
      vendors = data.vendors.filter((vendor) => typeof vendor.id === "string" && typeof vendor.name === "string");
      if (!vendors.length) throw new Error("厂商列表格式异常，请稍后重试。");
      vendorSelect.replaceChildren(...vendors.map((vendor) => {
        const option = document.createElement("option");
        option.value = vendor.id;
        option.textContent = vendor.name;
        return option;
      }));
      if (vendors.some((vendor) => vendor.id === "panda")) vendorSelect.value = "panda";
      vendorSelect.disabled = false;
      updateVendor();
      document.querySelector(".service-status").classList.remove("is-pending");
      $("service-status-text").textContent = "调试工具已就绪";
    } catch (error) {
      $("catalog-error-text").textContent = error instanceof TypeError
        ? "无法连接调试服务，请确认服务已启动后重试。"
        : error.message;
      $("catalog-error").hidden = false;
      $("service-status-text").textContent = "调试服务连接失败";
    } finally {
      $("retry-catalog").disabled = false;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedTool()) return;
    resetResult();
    const input = urlInput.value.trim();
    if (!input) {
      showMessage("请先粘贴当前可以正常进入游戏的完整 URL。", true);
      urlInput.setAttribute("aria-invalid", "true");
      urlInput.focus();
      return;
    }
    const currentRequest = requestId;
    controller = new AbortController();
    setLoading(true);
    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ vendor: vendorSelect.value, tool: selectedTool().id, url: input, validity: validitySelect.value }),
        signal: controller.signal,
      });
      const data = await readResponse(response);
      if (currentRequest !== requestId) return;
      if (typeof data.url !== "string" || typeof data.token !== "string" || !data.token) {
        throw new Error("服务未返回完整的调试链接，请重试。");
      }
      let generatedUrl;
      try { generatedUrl = new URL(data.url); } catch { throw new Error("服务返回的游戏链接格式不正确，请重试。"); }
      if (!["http:", "https:"].includes(generatedUrl.protocol)) {
        throw new Error("服务返回的游戏链接协议不正确，请重试。");
      }
      result = data;
      resultCard.classList.add("is-ready");
      $("result-url").value = data.url;
      $("result-token").value = data.token;
      $("open-game").href = data.url;
      const meta = [];
      if (typeof data.game === "string" && data.game) meta.push(data.game);
      if (typeof data.expires_label === "string" && data.expires_label) meta.push(data.expires_label);
      $("result-meta").textContent = meta.join(" · ");
      $("result-note").textContent = "已生成调试 Token，未在线验证登录会话。";
      $("result-empty").hidden = true;
      $("result-content").hidden = false;
      $("result-badge").hidden = false;
      showMessage("生成成功，可以复制新链接或直接打开游戏。");
    } catch (error) {
      if (currentRequest !== requestId || error.name === "AbortError") return;
      showMessage(error instanceof TypeError ? "无法连接调试服务，请确认服务正在运行后重试。" : error.message, true);
    } finally {
      if (currentRequest === requestId) {
        controller = null;
        setLoading(false);
      }
    }
  });

  function toast(text) {
    clearTimeout(toastTimer);
    $("toast").textContent = text;
    $("toast").hidden = false;
    toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3500);
  }

  async function copyResult(fieldId, label) {
    if (!result) return;
    const version = requestId;
    const field = $(fieldId);
    const value = field.value;
    if (!value) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(value);
      if (version === requestId) toast(`${label}已复制`);
    } catch {
      if (version !== requestId) return;
      const previousFocus = document.activeElement;
      field.focus();
      field.select();
      field.setSelectionRange(0, value.length);
      let copied = false;
      try { copied = document.execCommand("copy"); } catch { /* Keep selected text for manual copy. */ }
      if (copied) {
        previousFocus?.focus();
        toast(`${label}已复制`);
      } else {
        toast("已选中内容，请按 Ctrl+C 或 ⌘C 复制；手机可长按复制。");
      }
    }
  }

  urlInput.addEventListener("input", resetResult);
  validitySelect.addEventListener("change", resetResult);
  vendorSelect.addEventListener("change", updateVendor);
  $("clear-button").addEventListener("click", () => {
    urlInput.value = "";
    resetResult();
    urlInput.focus();
  });
  $("copy-url").addEventListener("click", () => copyResult("result-url", "游戏链接"));
  $("copy-token").addEventListener("click", () => copyResult("result-token", "调试 Token"));
  $("retry-catalog").addEventListener("click", loadVendors);
  // BFCache can restore form values without a new request. Never restore a generated credential.
  window.addEventListener("pageshow", (event) => { if (event.persisted) resetResult(); });
  loadVendors();
})();
