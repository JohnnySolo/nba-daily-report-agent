# 🏀 NBA Daily Report Agent: An Agentic AI Approach to On-Demand Sports Analytics

## 📑 Executive Summary
This project builds an autonomous AI agent that generates structured, evidence-backed NBA team reports on demand — delivered through a private Telegram bot.

The core challenge wasn't gathering data; it was **constraining a large language model to behave like a disciplined analyst** rather than a confident-sounding fabricator. Most LLM applications fail in production because the model "fills in" missing details under formatting pressure, drifts from instructions over long outputs, or recombines real-looking facts into false claims.

The system addresses this through layered prompt engineering: 8 hard constraints, a locked role taxonomy, cross-source validation, and a mandatory self-audit before every response — designed to fail loudly rather than hallucinate quietly.

The result is a working agent that consolidates statistics, scouting insight, key-player profiles, injury reports, and credible analytical articles into a single 6-section report, generated on demand from a Telegram chat.

---

## 📌 Project Overview

### 💼 The Analytical Problem & Product Objective
NBA fans, fantasy managers, and sports analysts face a fragmented information landscape:
- **Statistics** are buried in dozens of dashboards across multiple sites.
- **Injury reports** are scattered across team announcements, beat reporters, and aggregator pages of varying credibility.
- **Analytical commentary** sits behind paywalls, syndication networks, and ranking algorithms that surface live scores instead of strategic analysis.

**The objective:** Build an agent that consolidates these sources into a single structured report, prioritizing analytical depth over surface-level data, while enforcing strict factual discipline on the LLM that drives it.

### 📂 Data Sources & Tool Architecture
The agent retrieves data through 7 specialized tools:
* **NBA stats endpoints (`nba_api`):** Team standings, traditional + advanced metrics with league-wide ranks, recent game logs, player rotation data with minutes / FTA / 3PA needed for role detection.
* **Tavily search (domain-whitelisted):** Injury reports from credible outlets (NBA.com, ESPN, CBS Sports, Yahoo Sports), and analytical articles from premium sources (The Athletic, The Ringer, ESPN, NBA.com, Yahoo, CBS Sports).
* **Status gating:** Each tool call is preceded by a team-status check that determines which sections render — playoff teams, regular-season teams, and eliminated teams produce structurally different reports.

### 🛠️ Agent Methodology & Prompt Engineering
This is fundamentally a prompt-engineering project. The LLM (Claude Sonnet 4.5 via the Anthropic API) is treated not as a generator but as a constrained reasoner. The system prompt is ~13,000 characters of explicit rules, including:

* **Hard Constraints (8 total):** Inviolable rules covering fabrication, response format, source freshness, narrative-vs-injury source separation, long-term injury cross-validation, roster filtering, rank presence, and weakness-section padding. Violations are framed as failure modes, not guidelines.
* **Role Vocabulary (Locked List):** A 13-role + 2-modifier taxonomy for player classification (Primary scorer, Point forward, Defensive anchor, Sniper, Rim protector, etc.) with strict numeric criteria. Replaces vague descriptors with auditable thresholds.
* **Cross-Source Validation:** The injury logic explicitly cross-references player game count from the player tool against long-term-injury keywords from the injury source, preventing the agent from labeling active rotation players as "Out (long-term)" because old articles still surface their original injury.
* **Self-Audit Layer:** An 8-question checklist the model runs silently before output. Forces a pre-output reasoning pass that catches preamble leakage, missing ranks, padded weakness sections, and roster-filter violations.

### 📊 Output Structure & Behavioral Findings
Every report follows a fixed 6-section structure:

1. **Main Statistics** — Traditional and advanced metrics, every value paired with NBA rank (out of 30).
2. **Interesting Statistics** — Top-5 / bottom-5 league outliers + 3 winning-relevant trends from the last 10 games.
3. **Scouting Report** — Strengths and weaknesses, cross-validated between rank data and credible writer commentary. Disagreements between stats and articles resolved by claim type (quantifiable → stats win, qualitative → articles win).
4. **Key Players** — Top 3-5 rotation players sorted by minutes played, classified via the locked role taxonomy.
5. **Official Team Announcements** — Injury report with strict source-date and long-term-injury logic. Omitted for eliminated / offseason teams.
6. **Main Articles** — Up to 3 analytical pieces from a domain-whitelisted source pool, with title-level filtering to reject live-score pages and betting content.

**Key engineering finding:** Hard constraints framed as failure modes ("violation = failed response") significantly outperformed soft guidelines ("should" / "prefer"). When tested side-by-side, the soft-guideline version produced preamble leakage and padded weakness sections; the hard-constraint version eliminated both classes of error.

### ⚠️ Limitations & Acknowledged Trade-offs
To maintain stakeholder trust and avoid overclaiming what the agent can do:
* **Live-Game Data Stability:** During active games, NBA stat endpoints update mid-play. Reports run during games may show stats that shift by final. Phase A acknowledges this without auto-detecting; live-game blocking is deferred to Phase B.
* **Article Factual Verification:** Tavily returns articles by relevance, not factual accuracy. The agent trusts whitelisted domains but cannot verify article *content* against ground truth. A fabricated or speculative article from a real domain can flow through.
* **Playoff State Tracking:** The current status gate detects whether a team participated in the playoffs but not whether they're still alive. Eliminated teams may still be flagged as "Playoffs - active" until series-state tracking is added (Phase C).
* **Single-User Deployment:** Phase A is private (whitelisted to one user ID). Production-grade deployment with rate limiting, multi-user support, and 24/7 uptime is Phase B / C territory.

---

## 🏗️ Architecture

```
User (Telegram)
    ↓
telegram_bot.py        - whitelist auth, message routing, response chunking
    ↓
run.py                 - team-name resolution, agent invocation
    ↓
agent.py               - Claude Sonnet 4.5 + system prompt + tool registry
    ↓
tools.py (7 tools)
    ├── get_team_status          - playoffs / regular-season / eliminated detection
    ├── get_team_season_stats    - traditional per-game stats with NBA ranks
    ├── get_team_advanced_stats  - Net Rating, OffRtg, DefRtg, Four Factors
    ├── get_team_recent_games    - last 10 game logs
    ├── get_team_players         - top 7 by MPG with FTA/FG3A for role detection
    ├── get_team_injuries        - Tavily search across credible domains
    └── get_analytical_articles  - domain-whitelisted analytical content
    ↓
Data sources: nba_api (NBA.com endpoints), Tavily (web search)
```

---

## 🛠️ Tech Stack

- **LLM orchestration:** Claude Sonnet 4.5 via Anthropic API
- **Agent framework:** LangChain + LangGraph
- **Data:** nba_api (statistics), Tavily (news + injury search)
- **Bot interface:** python-telegram-bot
- **Language:** Python 3.12
- **Environment:** conda

---

## ⚙️ Setup

```bash
# Clone
git clone https://github.com/JohnnySolo/nba-daily-report-agent.git
cd nba-daily-report-agent

# Environment
conda create -n nba-agent python=3.12 -y
conda activate nba-agent
pip install -r requirements.txt

# Secrets - copy template and fill in your three keys
cp .env.example .env
# Then edit .env with your real keys

# Run agent in terminal
python run.py Celtics

# Or run as Telegram bot
python telegram_bot.py
```

Required environment variables in `.env`:
```
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...
TELEGRAM_BOT_TOKEN=...
```

To deploy your own private bot, edit `AUTHORIZED_USER_IDS` in `telegram_bot.py` to include your Telegram user ID.

---

## 🗺️ Roadmap (Phase B & Beyond)

- **Modular request routing** - brief / stats / scouting / injury / news / full report types selectable per query
- **Playoff-aware statistics** - playoff stats per series, with delta detection vs regular-season player baselines
- **Active-elimination detection** - true series-state tracking instead of binary playoff-participant flag
- **Scheduled daily push** - automatic morning report for a primary team
- **Multi-user support** - per-user team preferences, rate limiting, and cost controls

---

## 📜 License

MIT — see [LICENSE](LICENSE).
