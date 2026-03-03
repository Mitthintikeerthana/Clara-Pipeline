# Clara Pipeline

**Clara Answers: Zero-Cost Automation for Service Trade Businesses**

*Demo Call → Retell Agent → Onboarding Update → Agent v2*

A fully automated, version-controlled pipeline that transforms raw call transcripts into
production-ready Retell AI agent configurations — with structured diffs, changelogs,
and task-tracker integration. Runs on your laptop. Costs $0.

---

## What is Clara Answers?

Clara Answers is an AI-powered voice agent built using Retell that handles inbound calls
for service trade businesses including:

- **Fire protection companies**
- **Sprinkler and alarm contractors**
- **Electrical service providers**
- **HVAC and facility maintenance companies**
- **Plumbing services**

These businesses deal with:
- Emergency calls (e.g., sprinkler leak, fire alarm triggered)
- Non-emergency service requests
- Inspection scheduling
- After-hours routing requirements
- Integration constraints with systems like ServiceTrade

---

## The Client Journey

### Stage 1 – Demo Call (Exploratory and Value-Driven)

The demo call is **not** a configuration session. During the demo call:
- The client explains their pain points
- They describe current call handling problems
- They interact with an example Clara agent
- They experience the potential value of automation

**At this stage:**
- Business hours may not be fully discussed
- Emergency definitions may be vague
- Routing rules may be incomplete
- Integration constraints may not be detailed
- Some assumptions may still be open

The demo call gives us **directional understanding, not final specifications**.

**Pipeline A** generates a preliminary agent (v1) based only on what is explicitly stated.
**Do not invent missing configuration details.**

### Stage 2 – Purchase Decision

After the demo, if the client decides to move forward, they purchase the service.
Now we move from conceptual value to operational implementation.

### Stage 3 – Onboarding Call (Operational Precision)

The onboarding call is **configuration-focused**. This is where:
- Exact business hours are confirmed
- Time zones are finalized
- Emergency definitions are clearly defined
- After-hours routing logic is specified
- Transfer timeouts are decided
- Fallback logic is clarified
- Integration rules are confirmed
- Special constraints are introduced

**Examples:**
- "All emergency sprinkler calls must go directly to the phone tree."
- "Non-emergency extinguisher calls can be collected after hours."
- "Never create sprinkler jobs in ServiceTrade."
- "If transfer fails after 60 seconds, dispatch must be notified."

This stage **overrides or refines** the demo assumptions.

**Pipeline B** takes the demo-generated agent (v1) and updates it using onboarding data
to produce v2. It:
- Preserves version history
- Clearly logs changes
- Avoids overwriting unrelated fields
- Resolves conflicts logically and explicitly

### Optional Stage – Onboarding Form

Sometimes, instead of or in addition to a call, the client submits a structured
onboarding form. This form may:
- Clarify missing demo details
- Introduce new constraints
- Override previously assumed routing logic

The system merges structured form data with existing account data, applies updates
cleanly, flags conflicts, and regenerates the agent spec.

---

## Architecture & Data Flow

```
┌─────────────────── PIPELINE A ─────────────────────────────────────┐
│                                                                       │
│  inputs/demo/demo_NNN.txt                                            │
│       │                                                               │
│       ▼                                                               │
│  [Ingest] ──(audio?)──► [Whisper Transcription]                      │
│       │                          │                                    │
│       └──────────────────────────┘                                   │
│       ▼                                                               │
│  [LLM Extraction] ──► Account Memo JSON (v1)                        │
│  (Gemini free tier)                                                   │
│       ▼                                                               │
│  [Prompt Generator] ──► Retell Agent Spec + System Prompt (v1)      │
│       ▼                                                               │
│  [Storage] ──► outputs/accounts/<id>/v1/                            │
│       ▼                                                               │
│  [Task Tracker] ──► GitHub Issue created                            │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘

┌─────────────────── PIPELINE B ─────────────────────────────────────┐
│                                                                       │
│  inputs/onboarding/onboarding_NNN.txt                               │
│       │                                                               │
│       ▼                                                               │
│  [Ingest + Transcribe (if audio)]                                    │
│       ▼                                                               │
│  [LLM Update Extraction] ──► Patch JSON (what changed + why)        │
│       ▼                                                               │
│  [Apply Patches] ──► v2 Memo (v1 + updates)                         │
│       ▼                                                               │
│  [Prompt Generator] ──► Retell Agent Spec v2                        │
│       ▼                                                               │
│  [Diff Engine] ──► Structured diff + Changelog (JSON + Markdown)    │
│       ▼                                                               │
│  [Storage] ──► outputs/accounts/<id>/v2/                            │
│       ▼                                                               │
│  [Task Tracker] ──► GitHub Issue comment (v2 update)                │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Stack Choices (All Zero-Cost)

| Layer | Tool | Why |
|---|---|---|
| LLM | Google Gemini 1.5 Flash (AI Studio free tier) | 1,500 req/day, no card needed |
| Transcription | OpenAI Whisper (local) | Runs on-device, free forever |
| Storage | Local JSON files in directory structure | Reproducible, zero infra |
| Task Tracker | GitHub Issues (free tier) | Programmable via REST API |
| Orchestrator | Python scripts + n8n workflow export | Runnable both ways |
| Dashboard | Vanilla HTML + Python stdlib HTTP server | No build step, no deps |

---

## Project Structure

```
clara-pipeline/
├── scripts/
│   ├── config.py              # Central config (all values from env vars)
│   ├── extractor.py           # LLM + fallback extraction logic
│   ├── prompt_generator.py    # Retell agent spec & system prompt generator
│   ├── diff_engine.py         # v1 → v2 diff and changelog
│   ├── task_tracker.py        # GitHub Issues integration
│   ├── transcriber.py         # Whisper audio transcription
│   ├── pipeline_a.py          # Pipeline A orchestrator (demo → v1)
│   ├── pipeline_b.py          # Pipeline B orchestrator (onboarding → v2)
│   ├── batch_runner.py        # Batch: process all 10 files
│   └── utils/
│       ├── llm_client.py      # Gemini API client with retry logic
│       └── storage.py         # File-based JSON/text storage helpers
│
├── inputs/
│   ├── manifest.json          # Maps filenames ↔ account IDs
│   ├── demo/
│   │   ├── demo_001.txt       # ACE Plumbing & HVAC (Phoenix, AZ)
│   │   ├── demo_002.txt       # Blue Ridge Heating & Air (Charlotte, NC)
│   │   ├── demo_003.txt       # Sunrise Electrical Services (Miami, FL)
│   │   ├── demo_004.txt       # Mountain Peak HVAC (Denver, CO)
│   │   └── demo_005.txt       # Coastal Comfort Systems (San Diego, CA)
│   └── onboarding/
│       ├── onboarding_001.txt # ACE updates: Sunday hours, 3rd contact, new service
│       ├── onboarding_002.txt # Blue Ridge: new tech, Saturday summer hours
│       ├── onboarding_003.txt # Sunrise: temp contact swap, Broward expansion
│       ├── onboarding_004.txt # Mountain Peak: Sunday hours, new services
│       └── onboarding_005.txt # Coastal: Friday extension, emergency # change
│
├── outputs/
│   └── accounts/
│       └── <account_id>/
│           ├── v1/
│           │   ├── transcript.txt     # Raw/normalized transcript
│           │   ├── memo.json          # Structured account memo
│           │   ├── agent_spec.json    # Full Retell agent configuration
│           │   ├── agent_prompt.txt   # Human-readable system prompt
│           │   └── pipeline_meta.json # Run metadata, issue URL
│           └── v2/
│               ├── transcript.txt
│               ├── memo.json          # Updated memo
│               ├── agent_spec.json    # Updated agent spec
│               ├── agent_prompt.txt
│               ├── patch_result.json  # Raw LLM patch output
│               ├── changelog.json     # Structured diff
│               ├── changelog.md       # Human-readable diff
│               └── pipeline_meta.json
│
├── changelog/
│   └── <account_id>_v1_to_v2.md     # Global changelog copies
│
├── workflows/
│   └── n8n_workflow.json             # n8n import-ready workflow
│
├── dashboard/
│   ├── index.html                    # SPA dashboard
│   └── server.py                     # Stdlib HTTP server + JSON API
│
├── logs/
│   ├── <account>_pipeline_a.log
│   ├── <account>_pipeline_b.log
│   └── batch_summary.json
│
├── .env.example                      # Environment variable template
├── requirements.txt
└── README.md
```

---

## Prerequisites

- **Python 3.10+**
- **Google Gemini API key** (free) — [get one here](https://aistudio.google.com/)
- **GitHub token** (free, optional) — for task tracker issues
- **Whisper** (optional) — only needed for audio input files

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-username/clara-pipeline.git
cd clara-pipeline
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your keys
```

Minimum required for full LLM extraction:
```
GEMINI_API_KEY=your_key_here
```

For GitHub Issues task tracking (optional):
```
GITHUB_TOKEN=your_pat_here
GITHUB_REPO=your-username/your-repo
```

### 3. Load environment variables

**Linux / Mac:**
```bash
export $(grep -v '^#' .env | xargs)
```

**Windows (Command Prompt):**
```cmd
for /f "tokens=1,2 delims==" %i in (.env) do set %i=%j
```

**Windows (PowerShell):**
```powershell
Get-Content .env | ForEach-Object { if ($_ -notmatch '^#') { $v=$_.split('=',2); [Environment]::SetEnvironmentVariable($v[0],$v[1]) } }
```

---

## Running the Pipeline

### Option A: Run all 10 files at once (recommended)

```bash
python -m scripts.batch_runner
```

This runs Pipeline A on all 5 demo files, then Pipeline B on all 5 onboarding files.
Outputs are stored under `outputs/accounts/`.

```
═══════════════════════════════════════════════════════════
  BATCH COMPLETE
═══════════════════════════════════════════════════════════

  Pipeline A (Demo → v1)
  Account              Company                      Status   Time
  -------------------- ---------------------------- -------- -------
  ACE_PLB_001          ACE Plumbing & HVAC          ✓ ok       3.2
  BRH_002              Blue Ridge Heating & Air     ✓ ok       2.9
  ...

  Pipeline B (Onboarding → v2)
  Account              Company                      Status   Changes
  -------------------- ---------------------------- -------- --------
  ACE_PLB_001          ACE Plumbing & HVAC          ✓ ok          8
  ...
```

### Option B: Run a single pipeline step

```bash
# Pipeline A — one account
python -m scripts.pipeline_a \
  --input inputs/demo/demo_001.txt \
  --account_id ACE_PLB_001

# Pipeline B — one account (requires v1 to exist first)
python -m scripts.pipeline_b \
  --input inputs/onboarding/onboarding_001.txt \
  --account_id ACE_PLB_001
```

### Option C: Demo only or onboarding only

```bash
python -m scripts.batch_runner --demo-only        # Only Pipeline A
python -m scripts.batch_runner --onboarding-only  # Only Pipeline B
python -m scripts.batch_runner --account ACE_PLB_001  # One account only
```

---

## Dashboard

View all accounts, agent specs, and diffs in a browser:

```bash
python dashboard/server.py
# Open http://localhost:8080
```

The dashboard shows:
- All accounts with version badges
- Business hours, services, emergency contacts
- Side-by-side v1/v2 memos and prompts
- Interactive diff viewer with field-level changes
- Full Retell Agent Spec JSON

---

## n8n Workflow

### Import the workflow

1. Install n8n locally: `npm install -g n8n` or via Docker
2. Start n8n: `n8n start`
3. Open `http://localhost:5678`
4. Go to **Workflows → Import from File**
5. Select `workflows/n8n_workflow.json`
6. Set credentials: Add your `GEMINI_API_KEY` and `GITHUB_TOKEN` as n8n credentials
7. Activate the workflow

### Docker (quickstart)

```bash
docker run -it --rm \
  -p 5678:5678 \
  -e N8N_BASIC_AUTH_ACTIVE=false \
  -v n8n_data:/home/node/.n8n \
  n8nio/n8n
```

The n8n workflow models the full Pipeline A and B flow visually.
The Python scripts are the canonical execution engine; n8n provides
the orchestration view and webhook-based trigger option.

---

## Retell Agent Setup

### Free tier
1. Create an account at [https://app.retellai.com](https://app.retellai.com)
2. After running the pipeline, find the system prompt in:
   `outputs/accounts/<id>/v1/agent_prompt.txt`
3. In Retell UI → Agents → Create Agent:
   - Paste the system prompt content
   - Set voice to `openai-Alloy` (free tier default)
   - Configure phone number (requires Retell free credits)

### Programmatic import (if API key available)
```python
# Example: create agent via Retell API
import json, requests

spec = json.load(open("outputs/accounts/ACE_PLB_001/v1/agent_spec.json"))
resp = requests.post(
    "https://api.retellai.com/create-agent",
    headers={"Authorization": f"Bearer {RETELL_API_KEY}"},
    json={
        "agent_name": spec["agent_name"],
        "response_engine": spec["response_engine"],
        "voice_id": spec["voice_id"],
        "begin_message": spec["begin_message"],
    }
)
print(resp.json())
```

---

## Output Examples

### Account Memo (`memo.json`)
```json
{
  "account_id": "ACE_PLB_001",
  "company_name": "ACE Plumbing & HVAC",
  "business_hours": {
    "days": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"],
    "start": "07:00",
    "end": "18:00",
    "timezone": "America/Denver"
  },
  "office_address": "4521 West Washington Street, Phoenix, AZ 85003",
  "services_supported": ["Residential plumbing","Commercial HVAC","..."],
  "emergency_definition": ["Burst pipe","Sewage backup","No AC above 100°F","..."],
  "emergency_routing_rules": {
    "contacts": [
      {"name": "Dave Reyes", "phone": "602-555-0142", "order": 1},
      {"name": "Marcus Hill", "phone": "602-555-0198", "order": 2}
    ],
    "fallback": "Leave voicemail for both, advise 15-min callback"
  },
  ...
}
```

### Changelog (`changelog.json` excerpt)
```json
{
  "account_id": "ACE_PLB_001",
  "from_version": "v1",
  "to_version": "v2",
  "summary": "3 fields modified; 2 fields added",
  "changes": [
    {
      "field_path": "business_hours.days",
      "old_value": "[\"Monday\",\"Tuesday\",...,\"Saturday\"]",
      "new_value": "[\"Monday\",...,\"Sunday\"]",
      "change_type": "modified",
      "reason": "Sunday hours added (9AM-2PM) per onboarding call"
    },
    ...
  ]
}
```

---

## Idempotency

The pipeline is designed to be safely re-run:
- Re-running Pipeline A overwrites v1 outputs (same content if transcript unchanged)
- Re-running Pipeline B overwrites v2 outputs and regenerates the changelog
- GitHub Issues are created once per account (not duplicated on re-run if issue_url is cached in pipeline_meta.json)

---

## Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Gemini free tier rate limit (15 RPM) | Batch of 10 takes ~4 min with delays | Batch runner spaces requests automatically |
| No real-time clock for "is office open" | Agent can't detect current time | Pass `is_open` as a call variable in Retell |
| Whisper "base" model accuracy | ~90% WER on clean audio | Use "small" or "medium" for better accuracy |
| Rule-based fallback is limited | Misses complex extractions | Always use GEMINI_API_KEY when possible |
| Retell free tier has call credit limits | Can't make unlimited live calls | Agent spec is fully ready; credits needed for live calls |

---

## What Would Improve in Production

1. **Webhook-triggered ingestion** — Retell/Twilio posts call events → auto-triggers pipeline
2. **Supabase backend** — Replace JSON files with Postgres for queryability + row-level security
3. **Real-time `is_open` variable** — Inject current-time-aware open/closed status into Retell agent
4. **Slack/email alerts** — Notify ops when a new account is processed or a v2 diff is significant
5. **Human-in-the-loop review step** — Queue agent specs for human approval before Retell import
6. **Whisper large-v3** — Better transcription accuracy, especially for phone audio quality
7. **Confidence scoring** — LLM returns a confidence score per extracted field; low-confidence fields flagged automatically
8. **Multi-account deduplication** — Detect when two transcripts are for the same company under a different name

---

## Dataset

| File | Account ID | Company | Location |
|---|---|---|---|
| demo_001.txt | ACE_PLB_001 | ACE Plumbing & HVAC | Phoenix, AZ |
| demo_002.txt | BRH_002 | Blue Ridge Heating & Air | Charlotte, NC |
| demo_003.txt | SES_003 | Sunrise Electrical Services | Miami, FL |
| demo_004.txt | MPH_004 | Mountain Peak HVAC | Denver, CO |
| demo_005.txt | CCS_005 | Coastal Comfort Systems | San Diego, CA |

Each onboarding file corresponds to the same account and updates specific fields.

---

## Engineering Principles

This pipeline is designed to test and demonstrate:

### 1. Systems Thinking
- Clear separation between exploratory data (demo) and confirmed configuration (onboarding)
- Schema design for operational logic
- Safe automation that handles uncertainty

### 2. Responsible Data Handling
- **No hallucination**: Extract only explicitly stated information
- **No silent assumptions**: Flag missing data in `questions_or_unknowns`
- **Explicit confidence flags**: Track which fields are demo-derived vs onboarding-confirmed

### 3. Version Control Discipline
- v1 based on demo call (preliminary, may have gaps)
- v2 updated after onboarding (confirmed, production-ready)
- Complete changelog with reasons for each change
- Conflict detection and resolution tracking

### 4. Prompt Engineering
The agent prompt includes structured call flows:

**Business Hours Flow:**
1. Greeting
2. Ask purpose
3. Collect name and number
4. Transfer or route
5. Fallback if transfer fails
6. Ask if they need anything else
7. Close call

**After-Hours Flow:**
1. Greeting with hours disclosure
2. Ask purpose / check for emergency
3. If emergency: collect info first, then transfer
4. If transfer fails: apologize and assure follow-up
5. If non-emergency: collect details, confirm next-day callback
6. Ask if they need anything else
7. Close call

### 5. Robust Automation
- **Repeatable**: Same input produces same output
- **Batch-capable**: Process multiple accounts in sequence
- **Idempotent**: Re-running doesn't duplicate or corrupt data
- **Logged**: All operations recorded with timestamps
- **Reproducible**: Full audit trail from transcript to agent spec

### 6. Validation & Quality
- Schema validation for account memos
- Completeness scoring per category
- Confidence flags from LLM extraction
- Conflict detection between demo and onboarding

---

## Assignment Simulation

This pipeline simulates Clara's real onboarding automation challenge:

> **Human conversations → structured operational rules → AI agent configuration → production-ready prompt**

You are building the automation layer that converts messy, real-world conversation
into a deployable AI voice agent.

**Key Test Criteria:**
1. Clear separation between demo-derived assumptions (v1) and onboarding-confirmed rules (v2)
2. Intelligent handling of missing data (no hallucination, explicit `questions_or_unknowns`)
3. Clean versioning with changelog
4. Prompt discipline with explicit call flows
5. Robust, repeatable automation
