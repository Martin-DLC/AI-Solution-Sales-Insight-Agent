(function () {
  const form = document.getElementById("demo-form");
  if (!form) {
    return;
  }

  const statusText = document.getElementById("status-text");
  const errorBox = document.getElementById("error-box");
  const resultBadges = document.getElementById("result-badges");
  const mainOutputCard = document.getElementById("main-output-card");
  const evidenceCard = document.getElementById("evidence-card");
  const fallbackCard = document.getElementById("fallback-card");
  const enterpriseCard = document.getElementById("enterprise-card");
  const skillTraceCard = document.getElementById("skill-trace-card");
  const shadowCard = document.getElementById("shadow-card");
  const rawJsonCard = document.getElementById("raw-json-card");

  const examplePayload = {
    user_query: "一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
    industry: "SaaS",
    company_size: "中型",
    company_id: "demo_saas_001",
    target_goal: "提升销售转化和客户成功效率",
    current_systems: ["CRM", "客服系统"],
    constraints: ["不改变现有CRM主流程"],
    enable_shadow_retrieval: true,
    llm_mode: "deterministic"
  };

  bindTabs();

  document.getElementById("load-example-button").addEventListener("click", function () {
    applyPayload(examplePayload);
    setStatus("Loaded SaaS example. Click Run Agent to inspect the output.", false);
  });

  document.getElementById("clear-button").addEventListener("click", function () {
    form.reset();
    document.getElementById("enable_shadow_retrieval").checked = true;
    document.getElementById("llm_mode").value = "deterministic";
    resetPanels();
    setStatus("Ready. Load an example or enter a scenario to run the agent.", false);
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    resetPanels();
    setStatus("Running agent...", false, true);

    const payload = collectPayload();
    try {
      const response = await fetch("/solution-insight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();

      if (!response.ok) {
        setStatus("Agent request failed. Inspect the message and raw JSON below.", true);
        showError(extractErrorMessage(data));
        rawJsonCard.textContent = JSON.stringify(data, null, 2);
        activateTab("json");
        return;
      }

      renderResponse(data, payload.enable_shadow_retrieval);
      setStatus("Agent run completed.", false);
    } catch (error) {
      setStatus("Agent request failed before a valid response was returned.", true);
      showError("Unable to reach /solution-insight from the demo page.");
      rawJsonCard.textContent = JSON.stringify({ error: String(error) }, null, 2);
      activateTab("json");
    }
  });

  function bindTabs() {
    document.querySelectorAll(".tab-button").forEach(function (button) {
      button.addEventListener("click", function () {
        activateTab(button.dataset.tab);
      });
    });
  }

  function activateTab(tabName) {
    document.querySelectorAll(".tab-button").forEach(function (button) {
      button.classList.toggle("active", button.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach(function (panel) {
      panel.classList.toggle("active", panel.id === "tab-" + tabName);
    });
  }

  function collectPayload() {
    return {
      user_query: document.getElementById("user_query").value.trim(),
      industry: normalizeOptional(document.getElementById("industry").value),
      company_size: normalizeOptional(document.getElementById("company_size").value),
      company_id: normalizeOptional(document.getElementById("company_id").value),
      target_goal: normalizeOptional(document.getElementById("target_goal").value),
      current_systems: splitList(document.getElementById("current_systems").value),
      constraints: splitList(document.getElementById("constraints").value),
      enable_shadow_retrieval: document.getElementById("enable_shadow_retrieval").checked,
      llm_mode: document.getElementById("llm_mode").value
    };
  }

  function applyPayload(payload) {
    document.getElementById("user_query").value = payload.user_query || "";
    document.getElementById("industry").value = payload.industry || "";
    document.getElementById("company_size").value = payload.company_size || "";
    document.getElementById("company_id").value = payload.company_id || "";
    document.getElementById("target_goal").value = payload.target_goal || "";
    document.getElementById("current_systems").value = (payload.current_systems || []).join(", ");
    document.getElementById("constraints").value = (payload.constraints || []).join(", ");
    document.getElementById("enable_shadow_retrieval").checked = Boolean(payload.enable_shadow_retrieval);
    document.getElementById("llm_mode").value = payload.llm_mode || "deterministic";
  }

  function renderResponse(data, shadowEnabled) {
    hideError();
    renderBadges(data);
    renderOverview(data);
    renderEvidence(data.evidence_items || []);
    renderFallback(data);
    renderEnterpriseContext(data.enterprise_context);
    renderSkillTrace(data.skill_trace);
    renderShadowDebug(data.shadow_retrieval_debug, shadowEnabled);
    rawJsonCard.textContent = JSON.stringify(data, null, 2);
    activateTab("overview");
  }

  function renderBadges(data) {
    const badges = [
      createBadge("LLM: " + safeText(data.llm_mode)),
      createBadge("Evidence: " + safeText(String((data.evidence_items || []).length))),
      createBadge("Fallback: " + safeText(String(data.fallback_recommended)), data.fallback_recommended ? "warning" : "")
    ];
    resultBadges.innerHTML = badges.join("");
    resultBadges.classList.remove("hidden");
  }

  function renderOverview(data) {
    mainOutputCard.className = "content-stack";
    mainOutputCard.innerHTML = [
      "<div class='summary-grid'>",
      summaryCard("Requirement Summary", safeText(data.requirement_summary)),
      summaryCard("Proposed Solution", safeText(data.proposed_solution)),
      summaryCard("Pain Points", renderPills(data.pain_points)),
      summaryCard("AI Opportunity Points", renderPills(data.ai_opportunity_points)),
      "</div>"
    ].join("");
  }

  function renderEvidence(items) {
    evidenceCard.className = "content-stack";
    if (!items.length) {
      evidenceCard.innerHTML = "<p class='empty-state'>No evidence items returned.</p>";
      return;
    }
    evidenceCard.innerHTML = "<div class='evidence-list'>" + items.map(function (item) {
      return [
        "<article class='evidence-card'>",
        "<strong>" + safeText(item.title) + "</strong>",
        "<p><strong>candidate_type</strong> " + safeText(item.candidate_type) + "</p>",
        "<p><strong>citation_label</strong> " + safeText(item.citation_label) + "</p>",
        "<p><strong>document_id</strong> " + safeText(item.document_id) + "</p>",
        "<p><strong>chunk_id</strong> " + safeText(item.chunk_id || "-") + "</p>",
        "<p><strong>runtime_eligible</strong> " + safeText(String(item.runtime_eligible)) + "</p>",
        "<p><strong>rejection_reasons</strong> " + safeText((item.rejection_reasons || []).join(", ") || "-") + "</p>",
        "<p><strong>content_excerpt</strong> " + safeText(item.content_excerpt) + "</p>",
        "</article>"
      ].join("");
    }).join("") + "</div>";
  }

  function renderFallback(data) {
    fallbackCard.className = data.fallback_recommended ? "content-stack warning-surface" : "content-stack";
    fallbackCard.innerHTML = [
      "<div class='metric-grid'>",
      metricCard("Evidence Completeness", safeText(data.evidence_completeness)),
      metricCard("Fallback Recommended", safeText(String(data.fallback_recommended))),
      metricCard("Human Confirmation Required", safeText(String(data.human_confirmation_required))),
      metricCard("Fallback Reasons", renderPills(data.fallback_reasons)),
      "</div>"
    ].join("");
  }

  function renderEnterpriseContext(context) {
    enterpriseCard.className = "content-stack";
    if (!context) {
      enterpriseCard.innerHTML = "<p class='empty-state'>No enterprise context was attached to this run.</p>";
      return;
    }
    enterpriseCard.innerHTML = [
      "<div class='metric-grid'>",
      metricCard("provider_success_count", safeText(String(context.provider_success_count))),
      metricCard("provider_failed_count", safeText(String(context.provider_failed_count))),
      metricCard("provider_skipped_count", safeText(String(context.provider_skipped_count))),
      metricCard("context_source", safeText(context.context_source)),
      "</div>",
      "<div class='context-grid'>",
      contextCard("company_profile", context.company_profile),
      contextCard("crm_context", context.crm_context),
      contextCard("ticket_context", context.ticket_context),
      contextCard("bi_context", context.bi_context),
      contextCard("knowledge_context", context.knowledge_context),
      contextCard("provider_warnings", context.provider_warnings || []),
      "</div>"
    ].join("");
  }

  function renderSkillTrace(trace) {
    skillTraceCard.className = "content-stack";
    if (!trace) {
      skillTraceCard.innerHTML = "<p class='empty-state'>No skill trace returned.</p>";
      return;
    }
    skillTraceCard.innerHTML = [
      "<div class='metric-grid'>",
      metricCard("skill_count", safeText(String(trace.skill_count))),
      metricCard("failed_skill_count", safeText(String(trace.failed_skill_count))),
      metricCard("total_elapsed_ms", safeText(String(trace.total_elapsed_ms))),
      metricCard("warnings", renderPills(trace.warnings || [])),
      "</div>",
      "<div class='trace-list'>",
      traceCard("executed_skills", renderPills(trace.executed_skills || [])),
      "</div>"
    ].join("");
  }

  function renderShadowDebug(debugPayload, shadowEnabled) {
    shadowCard.className = "content-stack secondary-surface";
    const header = "<p class='shadow-note'>Shadow retrieval is diagnostic only and does not affect the formal answer.</p>";
    if (!shadowEnabled) {
      shadowCard.innerHTML = header + "<p>Shadow retrieval was disabled for this run.</p>";
      return;
    }
    if (!debugPayload) {
      shadowCard.innerHTML = header + "<p>No shadow debug payload returned.</p>";
      return;
    }
    shadowCard.innerHTML = [
      header,
      "<div class='metric-grid'>",
      metricCard("shadow summary", safeText(debugPayload.hierarchical_mode)),
      metricCard("candidate_count", safeText(String(debugPayload.candidate_count))),
      metricCard("document_candidate_count", safeText(String(debugPayload.document_candidate_count))),
      metricCard("chunk_candidate_count", safeText(String(debugPayload.chunk_candidate_count))),
      metricCard("runtime_eligible_count", safeText(String(debugPayload.runtime_eligible_count))),
      metricCard("runtime_rejected_count", safeText(String(debugPayload.runtime_rejected_count))),
      metricCard("shadow_error", safeText(debugPayload.shadow_error || "none")),
      metricCard("fallback_reasons", renderPills(debugPayload.fallback_reasons || [])),
      "</div>"
    ].join("");
  }

  function summaryCard(title, bodyHtml) {
    return "<article class='summary-card'><strong>" + safeText(title) + "</strong><div>" + bodyHtml + "</div></article>";
  }

  function metricCard(title, bodyHtml) {
    return "<article class='metric-card'><strong>" + safeText(title) + "</strong><div>" + bodyHtml + "</div></article>";
  }

  function contextCard(title, value) {
    return "<article class='context-card'><strong>" + safeText(title) + "</strong><pre>" + safeText(JSON.stringify(value, null, 2)) + "</pre></article>";
  }

  function traceCard(title, bodyHtml) {
    return "<article class='trace-card'><strong>" + safeText(title) + "</strong><div>" + bodyHtml + "</div></article>";
  }

  function renderPills(items) {
    if (!items || !items.length) {
      return "<span class='pill'>-</span>";
    }
    return "<div class='pill-list'>" + items.map(function (item) {
      return "<span class='pill'>" + safeText(String(item)) + "</span>";
    }).join("") + "</div>";
  }

  function setStatus(message, isError, isLoading) {
    statusText.textContent = message;
    const runButton = document.getElementById("run-agent-button");
    runButton.disabled = Boolean(isLoading);
    runButton.textContent = isLoading ? "Running..." : "Run Agent";
    if (!isError) {
      hideError();
    }
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  function hideError() {
    errorBox.textContent = "";
    errorBox.classList.add("hidden");
  }

  function resetPanels() {
    resultBadges.innerHTML = "";
    resultBadges.classList.add("hidden");
    mainOutputCard.className = "content-stack empty-state";
    mainOutputCard.innerHTML = "<h3>Requirement Summary</h3><p>Run the agent to populate the result console.</p>";
    evidenceCard.className = "content-stack empty-state";
    evidenceCard.innerHTML = "<h3>Evidence</h3><p>No evidence yet.</p>";
    fallbackCard.className = "content-stack empty-state";
    fallbackCard.innerHTML = "<h3>Fallback</h3><p>No fallback status yet.</p>";
    enterpriseCard.className = "content-stack empty-state";
    enterpriseCard.innerHTML = "<h3>Enterprise Context</h3><p>Choose a company context to inspect CRM, Ticket, BI, and Knowledge signals.</p>";
    skillTraceCard.className = "content-stack empty-state";
    skillTraceCard.innerHTML = "<h3>Skill Trace</h3><p>No skill trace yet.</p>";
    shadowCard.className = "content-stack empty-state secondary-surface";
    shadowCard.innerHTML = "<h3>Shadow Debug</h3><p class='shadow-note'>Shadow retrieval is diagnostic only and does not affect the formal answer.</p><p>Shadow diagnostics will appear here after a run.</p>";
    rawJsonCard.textContent = "{}";
    hideError();
    activateTab("overview");
  }

  function extractErrorMessage(payload) {
    if (payload && typeof payload === "object" && payload.detail) {
      if (typeof payload.detail === "string") {
        return payload.detail;
      }
      return "The request was rejected by the API.";
    }
    return "Unexpected API error.";
  }

  function splitList(value) {
    return value.split(",").map(function (item) {
      return item.trim();
    }).filter(Boolean);
  }

  function normalizeOptional(value) {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }

  function createBadge(label, variant) {
    return "<span class='badge" + (variant ? " badge-" + variant : "") + "'>" + safeText(label) + "</span>";
  }

  function safeText(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
})();
