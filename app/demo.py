from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def landing_page() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AI Solution Sales Insight Agent</title>
    <link rel="stylesheet" href="/static/demo.css">
  </head>
  <body class="landing-page">
    <main class="landing-shell">
      <section class="hero-panel">
        <div class="hero-copy">
          <p class="eyebrow">Portfolio-grade AI Agent Prototype</p>
          <h1>AI Solution Sales Insight Agent</h1>
          <p class="hero-description">
            A lightweight AI solution sales copilot demo that turns customer needs into structured insight,
            formal evidence, fallback guidance, enterprise context, and shadow diagnostics.
          </p>
          <div class="hero-actions">
            <a class="primary-button" href="/demo">Open Web Demo</a>
            <a class="secondary-button" href="/human-eval">Human Review</a>
            <a class="secondary-button" href="/docs">API Docs</a>
          </div>
        </div>
        <div class="hero-sidecard">
          <h2>Demo Principles</h2>
          <ul class="bullet-list">
            <li>Deterministic mode by default</li>
            <li>Shadow retrieval does not affect the formal answer</li>
            <li>Fallback protects evidence and boundary risks</li>
            <li>Do not expose this demo publicly without auth</li>
          </ul>
        </div>
      </section>
    </main>
  </body>
</html>
"""
    )


@router.get("/demo", response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Solution Insight Agent Demo</title>
    <link rel="stylesheet" href="/static/demo.css">
  </head>
  <body class="demo-page">
    <div class="app-shell">
      <header class="topbar">
        <div>
          <p class="eyebrow">Portfolio-grade AI Agent prototype</p>
          <h1>Solution Insight Agent Console</h1>
        </div>
        <nav class="topbar-links">
          <a href="/">Home</a>
          <a href="/human-eval">Human Review</a>
          <a href="/docs">API Docs</a>
        </nav>
      </header>

      <section class="announcement-grid">
        <article class="notice-card">
          <strong>Deterministic mode by default</strong>
          <p>Use deterministic mode for reproducible demos. Auto mode stays available for later live model wiring.</p>
        </article>
        <article class="notice-card">
          <strong>Shadow retrieval is diagnostic only</strong>
          <p>It never changes the formal answer or the formal evidence set.</p>
        </article>
        <article class="notice-card">
          <strong>Fallback protects evidence and boundary risks</strong>
          <p>When grounding is weak, the system surfaces caution instead of inventing certainty.</p>
        </article>
      </section>

      <main class="workspace-layout">
        <section class="left-column">
          <div class="panel form-panel">
            <div class="panel-heading">
              <h2>Run Agent</h2>
              <p>Input a customer scenario and inspect the agent response as a portfolio demo.</p>
            </div>
            <form id="demo-form" class="demo-form">
              <label for="user_query">Customer Need</label>
              <textarea id="user_query" name="user_query" rows="7" placeholder="Describe the customer scenario, pain, and target outcome." required></textarea>

              <div class="field-grid">
                <div>
                  <label for="industry">Industry</label>
                  <input id="industry" name="industry" type="text" placeholder="SaaS">
                </div>
                <div>
                  <label for="company_size">Company Size</label>
                  <input id="company_size" name="company_size" type="text" placeholder="中型">
                </div>
              </div>

              <div class="field-grid">
                <div>
                  <label for="company_id">Company Context</label>
                  <select id="company_id" name="company_id">
                    <option value="">No company context</option>
                    <option value="demo_saas_001">demo_saas_001</option>
                    <option value="demo_ecommerce_001">demo_ecommerce_001</option>
                    <option value="demo_manufacturing_001">demo_manufacturing_001</option>
                  </select>
                </div>
                <div>
                  <label for="llm_mode">LLM Mode</label>
                  <select id="llm_mode" name="llm_mode">
                    <option value="deterministic" selected>deterministic</option>
                    <option value="auto">auto</option>
                  </select>
                </div>
              </div>

              <label for="target_goal">Target Goal</label>
              <input id="target_goal" name="target_goal" type="text" placeholder="提升销售转化和客户成功效率">

              <label for="current_systems">Current Systems</label>
              <input id="current_systems" name="current_systems" type="text" placeholder="CRM, 客服系统">

              <label for="constraints">Constraints</label>
              <input id="constraints" name="constraints" type="text" placeholder="不改变现有CRM主流程">

              <label class="checkbox-row" for="enable_shadow_retrieval">
                <input id="enable_shadow_retrieval" name="enable_shadow_retrieval" type="checkbox" checked>
                <span>Enable shadow retrieval debug</span>
              </label>

              <div class="action-row">
                <button type="submit" id="run-agent-button" class="primary-button">Run Agent</button>
                <button type="button" id="load-example-button" class="secondary-button">Load SaaS Example</button>
                <button type="button" id="clear-button" class="ghost-button">Clear</button>
              </div>
            </form>
          </div>
        </section>

        <section class="right-column">
          <div id="status-card" class="panel status-panel">
            <div class="panel-heading">
              <h2>Status</h2>
              <p id="status-text">Ready. Load an example or enter a scenario to run the agent.</p>
            </div>
            <div id="error-box" class="error-box hidden"></div>
          </div>

          <div id="results-shell" class="panel results-panel">
            <div class="results-header">
              <div>
                <h2>Result Console</h2>
                <p>Requirement Summary, Evidence, Fallback, Enterprise Context, Skill Trace, Shadow Debug, and Raw JSON.</p>
              </div>
              <div id="result-badges" class="result-badges hidden"></div>
            </div>

            <div class="tabbar" role="tablist" aria-label="Demo result panels">
              <button class="tab-button active" type="button" data-tab="overview">Overview</button>
              <button class="tab-button" type="button" data-tab="evidence">Evidence</button>
              <button class="tab-button" type="button" data-tab="fallback">Fallback</button>
              <button class="tab-button" type="button" data-tab="enterprise">Enterprise Context</button>
              <button class="tab-button" type="button" data-tab="skills">Skill Trace</button>
              <button class="tab-button" type="button" data-tab="shadow">Shadow Debug</button>
              <button class="tab-button" type="button" data-tab="json">Raw JSON</button>
            </div>

            <section id="tab-overview" class="tab-panel active">
              <div id="main-output-card" class="content-stack empty-state">
                <h3>Requirement Summary</h3>
                <p>Run the agent to populate the result console.</p>
              </div>
            </section>

            <section id="tab-evidence" class="tab-panel">
              <div id="evidence-card" class="content-stack empty-state">
                <h3>Evidence</h3>
                <p>No evidence yet.</p>
              </div>
            </section>

            <section id="tab-fallback" class="tab-panel">
              <div id="fallback-card" class="content-stack empty-state">
                <h3>Fallback</h3>
                <p>No fallback status yet.</p>
              </div>
            </section>

            <section id="tab-enterprise" class="tab-panel">
              <div id="enterprise-card" class="content-stack empty-state">
                <h3>Enterprise Context</h3>
                <p>Choose a company context to inspect CRM, Ticket, BI, and Knowledge signals.</p>
              </div>
            </section>

            <section id="tab-skills" class="tab-panel">
              <div id="skill-trace-card" class="content-stack empty-state">
                <h3>Skill Trace</h3>
                <p>No skill trace yet.</p>
              </div>
            </section>

            <section id="tab-shadow" class="tab-panel">
              <div id="shadow-card" class="content-stack empty-state secondary-surface">
                <h3>Shadow Debug</h3>
                <p class="shadow-note">Shadow retrieval is diagnostic only and does not affect the formal answer.</p>
                <p>Shadow diagnostics will appear here after a run.</p>
              </div>
            </section>

            <section id="tab-json" class="tab-panel">
              <div class="content-stack">
                <h3>Raw JSON</h3>
                <pre id="raw-json-card">{}</pre>
              </div>
            </section>
          </div>
        </section>
      </main>
    </div>

    <script src="/static/demo.js"></script>
  </body>
</html>
"""
    )
