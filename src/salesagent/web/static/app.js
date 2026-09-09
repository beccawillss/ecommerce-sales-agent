"use strict";

(() => {
  const SESSION_KEY = "salesagent.session_id.v1";
  const CHAT_ENDPOINT = "/api/v1/chat";
  const MAX_MESSAGE_LENGTH = 4000;

  const chatForm = document.querySelector("#chat-form");
  const messageInput = document.querySelector("#message-input");
  const characterCount = document.querySelector("#character-count");
  const sendButton = document.querySelector("#send-button");
  const newConversationButton = document.querySelector("#new-conversation");
  const messages = document.querySelector("#messages");
  const welcome = document.querySelector("#welcome");
  const requestStatus = document.querySelector("#request-status");
  const requestError = document.querySelector("#request-error");
  const sessionNote = document.querySelector("#session-note");
  const starterButtons = Array.from(document.querySelectorAll("[data-prompt]"));

  if (
    !(chatForm instanceof HTMLFormElement) ||
    !(messageInput instanceof HTMLTextAreaElement) ||
    !(characterCount instanceof HTMLElement) ||
    !(sendButton instanceof HTMLButtonElement) ||
    !(newConversationButton instanceof HTMLButtonElement) ||
    !(messages instanceof HTMLElement) ||
    !(welcome instanceof HTMLElement) ||
    !(requestStatus instanceof HTMLElement) ||
    !(requestError instanceof HTMLElement) ||
    !(sessionNote instanceof HTMLElement)
  ) {
    return;
  }

  let sessionId = readStoredSessionId();
  let requestInFlight = false;
  let lastFailedSubmission = null;

  if (sessionId !== null) {
    sessionNote.hidden = false;
  }

  class UiRequestError extends Error {
    constructor(kind, status = null) {
      super(kind);
      this.name = "UiRequestError";
      this.kind = kind;
      this.status = status;
    }
  }

  function readStoredSessionId() {
    try {
      const value = window.sessionStorage.getItem(SESSION_KEY);
      return typeof value === "string" && value.trim() !== "" ? value : null;
    } catch {
      return null;
    }
  }

  function storeSessionId(value) {
    sessionId = value;
    try {
      window.sessionStorage.setItem(SESSION_KEY, value);
    } catch {
      // In-memory continuity remains available for this page lifetime.
    }
  }

  function clearSessionId() {
    sessionId = null;
    try {
      window.sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // Storage can be unavailable; the in-memory value is already cleared.
    }
  }

  function updateCharacterCount() {
    characterCount.textContent = `${messageInput.value.length} / ${MAX_MESSAGE_LENGTH}`;
  }

  function setBusy(isBusy) {
    requestInFlight = isBusy;
    sendButton.disabled = isBusy;
    messageInput.disabled = isBusy;
    newConversationButton.disabled = isBusy;
    starterButtons.forEach((button) => {
      if (button instanceof HTMLButtonElement) {
        button.disabled = isBusy;
      }
    });
    messages.setAttribute("aria-busy", String(isBusy));
  }

  function clearError() {
    requestError.textContent = "";
    requestError.hidden = true;
  }

  function showError(message) {
    requestError.textContent = message;
    requestError.hidden = false;
  }

  function errorMessageFor(error) {
    if (error instanceof UiRequestError) {
      if (error.kind === "http" && error.status === 500) {
        return "The concierge is temporarily unavailable. Your message is still here—please try again.";
      }
      if (error.kind === "http") {
        return "That message could not be sent. Review it and try again.";
      }
      if (error.kind === "response") {
        return "The concierge returned an unexpected response. Your message is still here—review it before trying again.";
      }
    }
    return "We couldn’t confirm the response. Your message is still here—review it before trying again.";
  }

  function createBubble(text, role) {
    const bubble = document.createElement("p");
    bubble.classList.add("message-bubble", `${role}-bubble`);
    bubble.textContent = text;
    return bubble;
  }

  function createTurn(role) {
    const turn = document.createElement("article");
    turn.classList.add("message-turn", `${role}-turn`);
    turn.setAttribute("aria-label", role === "shopper" ? "You" : "Sales Agent");
    return turn;
  }

  function appendShopperMessage(text) {
    if (
      lastFailedSubmission !== null &&
      lastFailedSubmission.text === text &&
      lastFailedSubmission.bubble.isConnected
    ) {
      lastFailedSubmission.bubble.classList.remove("failed");
      lastFailedSubmission.bubble.parentElement?.setAttribute("aria-label", "You");
      const reused = lastFailedSubmission.bubble;
      lastFailedSubmission = null;
      return reused;
    }

    welcome.hidden = true;
    const turn = createTurn("shopper");
    const bubble = createBubble(text, "shopper");
    turn.append(bubble);
    messages.append(turn);
    scrollToLatest();
    return bubble;
  }

  function appendAssistantResponse(response) {
    const turn = createTurn("assistant");
    const bubble = createBubble(
      response.message.trim() === ""
        ? "No conversational message was returned."
        : response.message,
      "assistant",
    );
    turn.append(bubble);
    appendStructuredResponse(turn, response);
    messages.append(turn);
    scrollToLatest();
  }

  function addTypingIndicator() {
    const turn = createTurn("assistant");
    turn.classList.add("typing-turn");
    turn.setAttribute("aria-hidden", "true");
    const bubble = document.createElement("div");
    bubble.classList.add("message-bubble", "assistant-bubble", "typing-indicator");
    for (let index = 0; index < 3; index += 1) {
      bubble.append(document.createElement("span"));
    }
    turn.append(bubble);
    messages.append(turn);
    scrollToLatest();
    return turn;
  }

  function scrollToLatest() {
    messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
  }

  function isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  function isNonBlankString(value) {
    return typeof value === "string" && value.trim() !== "";
  }

  function isFiniteNumberInRange(value, minimum, maximum = null) {
    return (
      typeof value === "number" &&
      Number.isFinite(value) &&
      value >= minimum &&
      (maximum === null || value <= maximum)
    );
  }

  function isNullableString(value) {
    return value === null || typeof value === "string";
  }

  function isNullablePercentage(value) {
    return value === null || isFiniteNumberInRange(value, 0, 100);
  }

  function decodeMatchedVariant(value) {
    if (value === null) {
      return null;
    }
    if (
      !isObject(value) ||
      typeof value.colour !== "string" ||
      typeof value.size !== "string" ||
      !Number.isInteger(value.stock) ||
      value.stock < 0
    ) {
      throw new UiRequestError("response");
    }
    return value;
  }

  function decodeRecommendation(value) {
    const availabilityValues = new Set([
      "in_stock",
      "out_of_stock",
      "partial",
      "unknown",
    ]);
    if (
      !isObject(value) ||
      !isNonBlankString(value.product_id) ||
      !isNonBlankString(value.name) ||
      !isFiniteNumberInRange(value.price, 0) ||
      value.currency !== "GBP" ||
      !isNonBlankString(value.product_url) ||
      !availabilityValues.has(value.availability) ||
      !(value.matched_variant === null || isObject(value.matched_variant))
    ) {
      throw new UiRequestError("response");
    }

    let parsedUrl;
    try {
      parsedUrl = new URL(value.product_url, window.location.origin);
    } catch {
      throw new UiRequestError("response");
    }
    if (
      !["http:", "https:"].includes(parsedUrl.protocol) ||
      parsedUrl.username !== "" ||
      parsedUrl.password !== ""
    ) {
      throw new UiRequestError("response");
    }

    decodeMatchedVariant(value.matched_variant);
    return value;
  }

  function decodePromotion(value) {
    if (value === null) {
      return null;
    }
    if (
      !isObject(value) ||
      typeof value.code !== "string" ||
      typeof value.valid !== "boolean" ||
      !isNullablePercentage(value.discount_percent) ||
      !isNullableString(value.reason)
    ) {
      throw new UiRequestError("response");
    }
    return value;
  }

  function decodePricing(value) {
    if (value === null) {
      return null;
    }
    if (
      !isObject(value) ||
      !isNonBlankString(value.product_id) ||
      !isFiniteNumberInRange(value.base_price, 0) ||
      !isFiniteNumberInRange(value.final_price, 0) ||
      value.currency !== "GBP" ||
      !isNullableString(value.discount_code) ||
      !isNullablePercentage(value.discount_percent)
    ) {
      throw new UiRequestError("response");
    }
    return value;
  }

  function decodeChatEnvelope(value, expectedSessionId) {
    if (
      !isObject(value) ||
      !isNonBlankString(value.session_id) ||
      !isNonBlankString(value.trace_id) ||
      typeof value.message !== "string" ||
      !Array.isArray(value.recommendations) ||
      value.recommendations.length > 3 ||
      !(value.promotion === null || isObject(value.promotion)) ||
      !(value.pricing === null || isObject(value.pricing))
    ) {
      throw new UiRequestError("response");
    }
    if (expectedSessionId !== null && value.session_id !== expectedSessionId) {
      throw new UiRequestError("response");
    }

    const recommendations = value.recommendations.map(decodeRecommendation);
    const recommendationIds = new Set(
      recommendations.map((recommendation) => recommendation.product_id),
    );
    if (recommendationIds.size !== recommendations.length) {
      throw new UiRequestError("response");
    }

    const promotion = decodePromotion(value.promotion);
    const pricing = decodePricing(value.pricing);
    if (pricing !== null) {
      if (
        !recommendationIds.has(pricing.product_id) ||
        promotion === null ||
        !promotion.valid ||
        (pricing.discount_code !== null &&
          pricing.discount_code !== promotion.code)
      ) {
        throw new UiRequestError("response");
      }
    }

    return { ...value, recommendations, promotion, pricing };
  }

  const availabilityLabels = {
    in_stock: "In stock",
    out_of_stock: "Out of stock",
    partial: "Some variants available",
    unknown: "Availability not confirmed",
  };

  function formatMoney(value, currency) {
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency,
    }).format(value);
  }

  function createRecommendationCard(recommendation) {
    const card = document.createElement("article");
    card.classList.add(
      "recommendation-card",
      `recommendation-${recommendation.availability}`,
    );

    const name = document.createElement("h3");
    name.textContent = recommendation.name;

    const price = document.createElement("p");
    price.classList.add("card-price");
    price.textContent = formatMoney(recommendation.price, recommendation.currency);

    const availability = document.createElement("p");
    availability.classList.add(
      "availability-badge",
      `availability-${recommendation.availability}`,
    );
    availability.textContent = availabilityLabels[recommendation.availability];

    card.append(name, price, availability);

    if (recommendation.matched_variant !== null) {
      const variant = document.createElement("p");
      variant.classList.add("variant-detail");
      variant.textContent = `Matched variant: ${recommendation.matched_variant.colour}, ${recommendation.matched_variant.size} · ${recommendation.matched_variant.stock} in stock`;
      card.append(variant);
    }

    const productLink = document.createElement("a");
    productLink.classList.add("product-link");
    productLink.href = recommendation.product_url;
    productLink.target = "_blank";
    productLink.rel = "noopener noreferrer";
    productLink.textContent = "View product (opens in a new tab)";
    card.append(productLink);

    return card;
  }

  function createPricingQuote(pricing) {
    const quote = document.createElement("section");
    quote.classList.add("pricing-quote");
    quote.setAttribute("aria-label", "Promotion price quote");

    const basePrice = document.createElement("p");
    basePrice.classList.add("quote-detail");
    basePrice.textContent = `Original quoted price: ${formatMoney(pricing.base_price, pricing.currency)}`;

    const finalPrice = document.createElement("p");
    finalPrice.classList.add("quote-price");
    finalPrice.textContent = `Final price: ${formatMoney(pricing.final_price, pricing.currency)}`;

    quote.append(basePrice, finalPrice);
    if (pricing.discount_code !== null || pricing.discount_percent !== null) {
      const detail = document.createElement("p");
      detail.classList.add("quote-detail");
      const parts = [];
      if (pricing.discount_code !== null) {
        parts.push(`Code ${pricing.discount_code}`);
      }
      if (pricing.discount_percent !== null) {
        parts.push(`${pricing.discount_percent}% off`);
      }
      detail.textContent = parts.join(" · ");
      quote.append(detail);
    }
    return quote;
  }

  function promotionMessage(promotion, hasPricing) {
    if (promotion.valid) {
      const percent =
        promotion.discount_percent === null
          ? ""
          : ` · ${promotion.discount_percent}% off`;
      const status = hasPricing
        ? "Validated for the quoted product"
        : "Validated; no product price was quoted";
      return `${promotion.code}${percent} — ${status}`;
    }
    if (promotion.reason === "inactive") {
      return `${promotion.code} — This promotion is inactive`;
    }
    if (promotion.reason === "unknown_code") {
      return `${promotion.code} — This promotion code is not recognised`;
    }
    return `${promotion.code} — This promotion is not available`;
  }

  function appendStructuredResponse(turn, response) {
    const cardsByProductId = new Map();

    if (response.recommendations.length > 0) {
      const region = document.createElement("section");
      region.classList.add("recommendation-region");
      region.setAttribute("aria-label", "Product recommendations");
      const grid = document.createElement("div");
      grid.classList.add("recommendation-grid");

      response.recommendations.forEach((recommendation) => {
        const card = createRecommendationCard(recommendation);
        cardsByProductId.set(recommendation.product_id, card);
        grid.append(card);
      });
      region.append(grid);
      turn.append(region);
    }

    if (response.pricing !== null) {
      const targetCard = cardsByProductId.get(response.pricing.product_id);
      if (targetCard === undefined) {
        throw new UiRequestError("response");
      }
      const productLink = targetCard.querySelector(".product-link");
      targetCard.insertBefore(
        createPricingQuote(response.pricing),
        productLink,
      );
    }

    if (response.promotion !== null) {
      const panel = document.createElement("section");
      panel.classList.add("promotion-panel");
      panel.setAttribute("aria-label", "Promotion status");
      const badge = document.createElement("span");
      badge.classList.add("promotion-badge");
      badge.textContent = response.promotion.valid ? "Valid code" : "Code unavailable";
      if (!response.promotion.valid) {
        badge.classList.add("promotion-invalid");
      }
      const detail = document.createElement("p");
      detail.textContent = promotionMessage(
        response.promotion,
        response.pricing !== null,
      );
      panel.append(badge, detail);
      turn.append(panel);
    }
  }

  async function postChat(message) {
    const expectedSessionId = sessionId;
    const payload = { message };
    if (expectedSessionId !== null) {
      payload.session_id = expectedSessionId;
    }

    let response;
    try {
      response = await window.fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
    } catch {
      throw new UiRequestError("network");
    }

    if (!response.ok) {
      throw new UiRequestError("http", response.status);
    }
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.toLowerCase().includes("application/json")) {
      throw new UiRequestError("response");
    }

    let body;
    try {
      body = await response.json();
    } catch {
      throw new UiRequestError("response");
    }
    return decodeChatEnvelope(body, expectedSessionId);
  }

  async function submitMessage() {
    if (requestInFlight) {
      return;
    }

    const message = messageInput.value;
    if (message.trim() === "") {
      showError("Enter a message before sending.");
      messageInput.focus();
      return;
    }
    if (message.length > MAX_MESSAGE_LENGTH) {
      showError("Keep your message to 4000 characters or fewer.");
      messageInput.focus();
      return;
    }

    clearError();
    const shopperBubble = appendShopperMessage(message);
    const typingTurn = addTypingIndicator();
    requestStatus.textContent = "Sales Agent is thinking…";
    setBusy(true);

    try {
      const response = await postChat(message);
      typingTurn.remove();
      appendAssistantResponse(response);
      storeSessionId(response.session_id);
      sessionNote.hidden = false;
      messageInput.value = "";
      updateCharacterCount();
      requestStatus.textContent = "";
      lastFailedSubmission = null;
    } catch (error) {
      typingTurn.remove();
      shopperBubble.classList.add("failed");
      shopperBubble.parentElement?.setAttribute(
        "aria-label",
        "You — message not answered",
      );
      lastFailedSubmission = { text: message, bubble: shopperBubble };
      requestStatus.textContent = "";
      showError(errorMessageFor(error));
    } finally {
      setBusy(false);
      messageInput.focus();
    }
  }

  function resetConversation() {
    if (requestInFlight) {
      return;
    }
    clearSessionId();
    lastFailedSubmission = null;
    messages.replaceChildren(welcome);
    welcome.hidden = false;
    sessionNote.hidden = true;
    requestStatus.textContent = "";
    clearError();
    messageInput.value = "";
    updateCharacterCount();
    messageInput.focus();
  }

  chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitMessage();
  });

  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });

  messageInput.addEventListener("input", updateCharacterCount);
  newConversationButton.addEventListener("click", resetConversation);
  starterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!(button instanceof HTMLButtonElement) || requestInFlight) {
        return;
      }
      messageInput.value = button.dataset.prompt ?? "";
      updateCharacterCount();
      messageInput.focus();
    });
  });

  updateCharacterCount();
})();
