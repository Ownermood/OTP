# 🔥 FINAL EXECUTION MANDATE — FIX → TEST → REBUILD → VERIFY

> **THIS SECTION OVERRIDES ANY AMBIGUITY IN THE DOCUMENT.**
>
> This is NOT an audit-only task.
> This is NOT a planning-only task.
> This is NOT a "write code and stop" task.
>
> **The required outcome is:**
>
> **INSPECT → FIND REAL PROBLEMS → FIX THEM → TEST → FIX FAILURES → TEST AGAIN → REBUILD/RESTART → REAL-FLOW VERIFY → REPORT HONESTLY**

## 0. DO THE WORK — DO NOT JUST DESCRIBE IT

If implementation access is available, **actually modify the repository**.

Do not respond with:
- "I recommend..."
- "this should be changed..."
- "planned for Phase X..."
- "the UI can be improved..."
- "tests should be added..."

when the requirement is actionable and the environment allows implementation.

For every in-scope defect:
1. Locate the actual implementation.
2. Reproduce or trace the defect.
3. Identify the root cause.
4. Implement the smallest safe fix.
5. Add/update the relevant test.
6. Run the test.
7. If it fails, fix the root cause.
8. Re-run the test.
9. Run regression tests.
10. Only then move to the next defect.

## 1. NO AUDIT-ONLY STOP

The previous audit/documentation is a **baseline**, not the final deliverable.

Do not stop after producing:
- an audit
- a list of P1–P20 issues
- a plan
- acceptance criteria
- a design proposal
- a list of files to change

Those are inputs to implementation.

If an issue is confirmed and is in scope, **fix it**.

If an issue is not safe to fix because of a concrete environment/access limitation, mark it `🚫 BLOCKED` and explain exactly what is missing.

## 2. FIX KNOWN DEFECTS FIRST

Prioritize known defects from the existing audit and repository reality, especially:
- broken/error states that strand users
- missing/weak command navigation
- unexpected-text silence
- stale OTP waiting/refresh behavior
- missing copy affordances
- incorrect button semantics
- insufficient-balance UX
- manual deposit input and validation
- quick-pick convenience without removing manual entry
- incomplete localization
- weak loading/empty states
- stale payment/navigation callbacks
- referral copy UX
- custom-emoji validation/registry/fallback
- throttle/cache/performance issues that are worth fixing safely

Do not claim an audit item is fixed until the actual implementation and tests support that claim.

## 3. FIX ORDER

Use this order unless actual repository dependencies require a safer order:

### A. Safety / correctness blockers
- wallet/accounting
- payment approval/idempotency
- authorization
- callback validation
- price authority
- provider state integrity
- database integrity

### B. Broken user flows
- errors
- loading
- empty states
- navigation
- FSM/cancel/back/home
- stale callbacks
- OTP/order continuity

### C. Fixed product requirements
- manual deposit amount
- ₹50 minimum
- insufficient balance UX
- catalogue/search/filter/pagination
- orders/history/account/referral/help
- localization

### D. Premium UI/UX
- design system
- button semantics
- message hierarchy
- spacing/readability
- custom emoji
- copy affordances

### E. Performance
- only evidence-based optimizations
- never trade correctness for speed

## 4. TEST AFTER EVERY MEANINGFUL FIX

Minimum loop:

```text
CHANGE
  ↓
FOCUSED TEST
  ↓
FAIL?
 ├─ YES → ROOT CAUSE → FIX → FOCUSED TEST AGAIN
 └─ NO
  ↓
RELATED REGRESSION TESTS
  ↓
NEXT CHANGE
```

Do not make 30 unrelated changes and only then run tests.

If a phase contains several tightly coupled changes, test the smallest meaningful unit first, then the integrated flow.

## 5. FULL REGRESSION BEFORE REBUILD

Before rebuilding/restarting the bot:

Run, as applicable:

```bash
pytest -q
ruff check .
git diff --check
```

Also run:
- migration validation if schema changed
- focused security tests
- wallet/payment tests
- callback/FSM tests
- provider mock/integration tests
- custom-emoji tests
- relevant UI/handler tests

The historical `419 passed` result is only a baseline. It is NOT proof of the current state.

## 6. REBUILD / RESTART GATE

**Do not rebuild/restart just because code was edited.**

Rebuild/restart only after:
- focused tests pass
- relevant regression tests pass
- full suite passes or any failure is explicitly explained
- lint/diff checks pass
- migration is reviewed if applicable
- no secret/config values were exposed
- no unsafe database operation occurred

### Rebuild means:
- rebuild/reinstall only if the project's runtime/deployment requires it
- otherwise restart/reload the bot using the project's existing safe mechanism
- do not invent a new deployment system
- do not delete/recreate the database
- do not change production credentials
- do not perform real purchases/deposits

After rebuild/restart:
1. Confirm process starts.
2. Confirm startup checks succeed.
3. Confirm database connection.
4. Confirm provider connectivity where safe.
5. Confirm no startup traceback.
6. Confirm the bot is actually polling/serving.
7. Perform real Telegram smoke tests if access is available.

## 7. POST-REBUILD REAL-FLOW VERIFICATION

At minimum, verify the changed flows in the actual Telegram UI when possible:

### Home
- `/start`
- balance visible
- Shop/Buy
- Deposit
- Orders
- Account
- Help

### Deposit
- manual amount entry
- `49` rejected
- `50` accepted
- invalid text rejected
- payment state correct
- Cancel works
- no balance credit before approval

### OTP
- catalogue
- country
- service
- price
- confirmation
- insufficient balance
- order state
- refresh
- OTP display only after provider confirmation

### SMM
- category/platform/service
- quantity validation
- confirmation
- order/status

### UX
- Back
- Home
- Cancel
- Retry
- Empty state
- Unexpected text
- Copy affordance
- Custom emoji/fallback

**Do not perform a real financial purchase unless explicitly authorized.**

## 8. IF REAL TELEGRAM TESTING IS BLOCKED

Do NOT pretend the UI was verified.

Report:

```text
TELEGRAM SMOKE TEST: 🚫 BLOCKED
Reason: <exact environment/access limitation>
What was tested instead: <tests/trace>
What remains unverified: <exact flows>
```

Code-level tests do not equal visual Telegram verification.

## 9. CUSTOM EMOJI — HARD RULE

The approved pack URLs are source packs, not IDs.

Never invent an ID.

For every production custom emoji:
- semantic role
- actual `custom_emoji_id`
- source pack
- fallback Unicode
- verification status
- evidence

If actual ID extraction is unavailable:
- keep the ID empty/null
- use fallback
- mark `UNVERIFIED` or `BLOCKED`
- continue the bot without custom emoji dependency

A fake ID is worse than a missing emoji.

## 10. MEMORY MUST BE UPDATED AFTER WORK

After each completed phase/update:
- record current phase
- record exact files changed
- record tests and exact results
- record runtime/UI verification
- record blocked items
- record known remaining issues
- record next action

Do not write "done" into Memory unless the evidence supports it.

## 11. FINAL RELEASE DECISION

There are only three acceptable outcomes:

### ✅ RELEASE-READY
All critical requirements are implemented and verified to the extent the environment allows.

### ⚠️ RELEASE WITH KNOWN LIMITATIONS
Non-critical items remain, clearly documented.

### 🚫 BLOCKED
A critical requirement cannot be verified or safely completed because of a concrete environment/access limitation.

Never call the project "complete" simply because it compiles or tests pass.

## 12. FINAL REPORT MUST BE FACTUAL

End with:

- **IMPLEMENTED:** exact changes
- **FIXED:** exact defects resolved
- **TESTED:** exact commands/results
- **REBUILT/RESTARTED:** exact action/result
- **TELEGRAM VERIFIED:** exact flows observed
- **TRACED:** exact items manually traced
- **INFERRED:** exact items inferred only
- **BLOCKED:** exact limitations
- **FILES CHANGED:** exact paths
- **DATABASE:** exact impact
- **SECURITY:** exact checks
- **PERFORMANCE:** exact changes/measurements
- **REMAINING:** real remaining work
- **GIT:** exact status/diff summary
- **COMMIT:** `NOT COMMITTED — waiting for explicit user approval`

# 🔴 FINAL COMMAND

**FIX IT. TEST IT. IF IT FAILS, FIX IT AGAIN. TEST AGAIN. ONLY AFTER TESTS PASS, REBUILD/RESTART. THEN VERIFY THE REAL TELEGRAM FLOW. THEN REPORT THE TRUTH.**


# 🚀 OTP BOT — ULTIMATE MASTER MD
## Complete Product + Architecture + Rules + Phases + Design + Memory + Verification Specification

> **Purpose:** This single Markdown file consolidates the complete contents of the project's PRD, Architecture, Rules, Phases, Design, Memory, and the detailed Master Product/UX/Verification specification into one source document for Claude Code.

> **IMPORTANT:** This document is an instruction/specification document. It does **not** claim that any requirement has already been implemented. Implementation status must always be verified from the actual repository, tests, runtime and UI.

---

# TABLE OF CONTENTS

1. Unified Project Mission
2. PRD — Product Requirements
3. Architecture — Technical Structure
4. Rules — Non-Negotiable Guardrails
5. Design — Premium Telegram UI/UX
6. Phases — Implementation Roadmap
7. Memory — Persistent Project State
8. Master Product + UX + Verification Protocol
9. Custom Emoji Pack Inventory & ID Rules
10. Deposit / Wallet Contract
11. OTP/SMS Marketplace Contract
12. SMM Contract
13. Error / Loading / Empty-State Contract
14. Database / Money / Security Contract
15. Testing & Verification Protocol
16. Performance Protocol
17. Release Gate
18. Final Definition of Done
19. Final Reporting Template

---

# ==============================================================================
# SOURCE DOCUMENT: README
# ==============================================================================

# 🚀 OTP BOT — FINAL DOCUMENTATION SYSTEM

## Why this structure exists

The OTP Bot project should not rely on one giant instruction file alone.
The documentation is split into six focused MDs so Claude Code can retain
product intent, architecture, guardrails, execution order, UI decisions and
session state without repeatedly reconstructing the whole project.

| File | Purpose |
|---|---|
| `PRD.md` | What is being built, for whom, and what success means |
| `Architecture.md` | How the existing system is structured and how changes fit into it |
| `Rules.md` | Non-negotiable engineering/security/product boundaries |
| `Phases.md` | Controlled implementation and verification roadmap |
| `Design.md` | Telegram UI/UX and premium visual system |
| `Memory.md` | Persistent project state and AI handoff context |

## Order Claude should read

1. `PRD.md`
2. `Architecture.md`
3. `Rules.md`
4. `Design.md`
5. `Phases.md`
6. `Memory.md`
7. `OTP_Bot_Master_Product_UX_Verification_Prompt.md` for the complete detailed specification

## Single source of truth

The six files organize the project. The complete master prompt contains the
detailed requirements and verification protocol. If a conflict appears,
security/data integrity and explicitly fixed owner requirements take priority.

## Workflow

READ → AUDIT → ACCEPTANCE CRITERIA → IMPLEMENT → TEST → TRACE/RUN →
REGRESSION → VISUAL VERIFY → UPDATE MEMORY → HONEST REPORT

## Never

- fabricate verification
- invent custom emoji IDs
- expose secrets
- delete `bot.db`
- commit without approval
- mark blocked work as complete

---

# ==============================================================================
# SOURCE DOCUMENT: PRD
# ==============================================================================

# OTP BOT — PRD (Product Requirements Document)

## 1. Product
A premium, production-grade Telegram OTP/SMS + SMM marketplace.

## 2. Product Objective
Transform the existing functional bot into a fast, polished, Telegram-native marketplace without breaking:
- existing business logic
- provider integrations
- wallet accounting
- payment validation
- database integrity
- authorization
- callback security
- OTP/SMS flows
- SMM flows
- admin/reviewer flows

## 3. Target Experience
Users must immediately understand:
- who they are
- their balance
- what they can buy
- the price
- where to click
- where their orders are
- where their OTP is
- how to deposit
- how to get support

## 4. Core Features
- Home/dashboard
- Wallet/deposit
- Manual deposit amount entry with ₹50 minimum
- UPI/QR payment flow
- OTP/SMS marketplace
- Country/service catalogue
- SMM catalogue and ordering
- Active orders/history
- Account/profile
- Referral
- Help/support
- Admin/reviewer controls
- Localized UI
- Telegram custom-emoji system with safe fallbacks

## 5. Fixed Deposit Requirement
- User must be able to type the amount manually.
- Minimum: ₹50.
- ₹49 → reject.
- ₹50 → accept.
- Quick-pick amounts are optional shortcuts only.
- Server-side validation is mandatory.
- Wallet credit occurs only after verified approval.
- Never trust client/callback amounts.

## 6. Success Criteria
The product is successful when the important flows are:
- understandable
- visually consistent
- safe
- fast
- recoverable
- regression-tested
- honestly verified

## 7. Quality Bar
Premium means clarity, hierarchy, consistency, speed and polish — not emoji spam.

## 8. Source of Truth
This PRD must be read together with Architecture.md, Rules.md, Phases.md,
Design.md and Memory.md.

---

# ==============================================================================
# SOURCE DOCUMENT: ARCHITECTURE
# ==============================================================================

# OTP BOT — ARCHITECTURE

## 1. Existing Technical Direction
- Python 3.11
- aiogram 3.x
- async SQLAlchemy 2.x
- Alembic
- pydantic-settings
- httpx
- structlog
- Telegram Bot API
- OTP/SMS providers
- SMM providers
- repository/service architecture
- localized messages
- integer minor-unit money
- transactional wallet logic
- callback authorization/validation
- idempotency

## 2. Layering
Prefer the existing architecture:
Telegram handlers
→ validation/state
→ services
→ repositories/providers
→ database/external APIs
→ Telegram response.

Do not rewrite stable architecture merely for aesthetics.

## 3. Major Domains
### Telegram/UI
- handlers
- keyboards
- callback data
- rendering
- localization
- custom emoji abstraction

### Commerce
- catalogue
- pricing
- offers
- orders
- wallet
- deposits/payments

### Providers
- SMS/OTP providers
- SMM providers

### Persistence
- models
- repositories
- migrations
- transactional/idempotent operations

### Operations
- startup/shutdown
- workers/background tasks
- logging
- throttling
- admin/reviewer flows

## 4. Security Boundaries
Authorization, callback validation, server-side pricing, transaction boundaries
and idempotency remain authoritative.

## 5. Emoji Architecture
Create one semantic registry. Handlers must request semantic icons such as
`shop`, `wallet`, `otp`, `success`, etc. They must not contain scattered raw IDs.

Every custom emoji needs a Unicode/text fallback.

## 6. Data Flow
Never trust:
- client-supplied price
- callback-supplied price
- callback authorization
- screenshots as payment proof by themselves

Re-read authoritative state before financial mutation.

## 7. Database
Preserve:
- integer money representation
- atomic balance changes
- transaction boundaries
- duplicate protection
- rollback behavior
- restart recovery

## 8. Integration Boundaries
Provider failures must become controlled user-facing states rather than
uncaught crashes or false success messages.

---

# ==============================================================================
# SOURCE DOCUMENT: RULES
# ==============================================================================

# OTP BOT — RULES / ENGINEERING GUARDRAILS

## 1. Absolute Rules
1. Never commit without explicit user approval.
2. Never delete or casually overwrite `bot.db`.
3. Never expose tokens, API keys, passwords, `.env` values, private credentials or sessions.
4. Never weaken authorization, callback validation, idempotency or payment safety.
5. Do not make unrelated changes.
6. Do not add unnecessary dependencies.
7. Do not blindly copy reference branding/assets/source.
8. Existing business behavior remains stable unless explicitly approved.
9. Test every meaningful change.
10. Never fabricate verification.

## 2. Verification Labels
- ✅ VERIFIED — actually executed/directly observed.
- 🧩 TRACED — manually walked through with concrete values.
- ⚠️ INFERRED — reasoned from code but not executed/fully traced.
- 🚫 BLOCKED — unable to verify for a concrete reason.

Never upgrade TRACED/INFERRED/BLOCKED to VERIFIED.

## 3. Money Rules
- Use integer minor units/project-safe representation.
- No floating-point financial arithmetic.
- ₹50 minimum deposit.
- Reject invalid, negative, zero and malformed amounts.
- Credit only after authoritative approval.
- Duplicate approval must not double-credit.

## 4. Callback / Authorization Rules
- Validate ownership and authorization server-side.
- Never trust prices or state encoded only in callbacks.
- Prevent replay and duplicate actions.

## 5. UI Rules
- Predictable buttons.
- Clear next action.
- No dead ends.
- No huge text walls.
- No emoji spam.
- Loading/error/empty states must be useful.
- Prefer editing existing messages when safe.

## 6. Custom Emoji Rules
Approved source packs:
- SoLo_HaMiD — https://t.me/addemoji/SoLo_HaMiD
- AnimatedIconic — https://t.me/addemoji/AnimatedIconic
- getmodpc — https://t.me/addemoji/getmodpc
- CenterOfEmoji22890889 — https://t.me/addemoji/CenterOfEmoji22890889
- vector_icons_by_fStikBot — https://t.me/addemoji/vector_icons_by_fStikBot

Pack links are NOT custom emoji IDs.
Never invent numeric IDs.
Only verified `custom_emoji_id` values enter the production registry.
Missing/invalid IDs must fall back safely.

## 7. Testing Rules
For relevant changes test:
- happy path
- failure path
- edge/boundary cases
- repeated clicks
- concurrency where relevant
- timeout/API failure
- restart/expired state
- unauthorized/tampered input

## 8. Failure Handling
Observe → Reproduce → Isolate → Root Cause → Fix → Retest → Regression test.

Never hide failures merely to make CI green.

---

# ==============================================================================
# SOURCE DOCUMENT: PHASES
# ==============================================================================

# OTP BOT — PHASES / EXECUTION ROADMAP

## Phase 0 — Reality Check
Declare whether the environment can actually run the project.

## Phase 1 — Before-State Audit
No modifications.
Inspect repository, architecture, UI, payments, OTP, SMM, database,
providers, callbacks, localization, tests and runtime constraints.

Deliver:
- findings
- risks
- exact files
- acceptance criteria
- test plan

## Phase 2 — Design System
Implement only approved shared conventions:
- rendering helpers
- semantic emoji abstraction
- button conventions
- formatting/localization conventions

Verify before continuing.

## Phase 3 — Home
Improve:
- balance visibility
- Shop/Buy
- Deposit
- Account
- Orders/History
- Help
- hierarchy and navigation

## Phase 4 — Deposit
Highest safety scrutiny.
Implement/verify:
Amount → Payment Method → QR/UPI → Paid → UTR/Receipt →
Pending → Review → Approved/Rejected.

Verify all money invariants.

## Phase 5 — OTP/SMS Marketplace
Improve:
- provider/server
- country selection
- search/filter
- service selection
- offers/pricing
- confirmation
- active order
- SMS/OTP
- expiry/cancellation/failure states

## Phase 6 — SMM
Improve:
- categories
- platforms
- service search
- details
- quantity
- order
- history/status

## Phase 7 — Micro-UX
Fix:
- Back/Home/Cancel
- loading
- errors
- empty states
- retry
- refresh
- copy affordances where supported

## Phase 8 — Performance
Evidence-based only:
- repeated DB calls
- N+1
- provider calls
- Telegram calls
- excessive edits
- blocking work

## Phase 9 — Security Review
Re-audit:
- auth
- callbacks
- payment manipulation
- replay
- idempotency
- provider abuse
- data exposure

## Phase 10 — Release Gate
Run relevant tests, inspect diff, verify runtime/UI where possible,
document blocked items, and wait for explicit commit approval.

## Rule
Do not rewrite the entire app in one giant pass. Finish and verify one
phase before moving to the next.

---

# ==============================================================================
# SOURCE DOCUMENT: DESIGN
# ==============================================================================

# OTP BOT — DESIGN SYSTEM / UX SPEC

## 1. Visual Direction
Premium Telegram-native marketplace:
- clean
- compact
- high hierarchy
- mobile-readable
- consistent
- fast
- trustworthy

## 2. Home
Primary:
- 🛒 Shop / Buy
- 💳 Deposit

Secondary:
- 👤 Account
- 📦 Orders / History
- 🎁 Referral where applicable
- ❓ Help

Balance must be prominent.

## 3. Navigation
Standard semantic actions:
- ← Back
- 🏠 Home
- ✕ Cancel
- ✓ Confirm
- → Continue
- 🔄 Refresh
- 🔎 Search
- ← Previous
- Next →

No dead ends.

## 4. Catalogue
Country item example:
`🇮🇳 India +91 | ₹XX`

Expose where reliable:
- flag
- country
- dial code
- price
- stock

Support:
- search
- filters
- A–Z
- pagination
- show all

## 5. OTP Order Card
Show:
- country
- service
- number
- price
- timer
- status
- next action

Never claim an OTP exists without provider confirmation.

## 6. Deposit UI
Show:
- amount
- payment method
- UPI
- QR
- exact instructions
- UTR/reference requirements
- pending state
- request/reference ID where appropriate
- next action

## 7. Status Language
- 🟡 Pending
- 🔵 Processing
- 🟢 Completed
- 🔴 Failed
- ⚪ Cancelled
- ⏳ Waiting for SMS

## 8. Error / Loading / Empty
Every error answers:
WHAT happened?
WHY, if safe?
NEXT action?

Loading must not spam Telegram with edits.
Empty states must provide a useful action.

## 9. Custom Emoji
Semantic roles include:
brand, header, home, shop, wallet, deposit, payment, QR, account,
profile, orders, history, referral, phone, number, SMS, OTP, country,
service, SMM, search, filter, sort, back, next, previous, confirm,
cancel, success, error, warning, info, waiting, pending, processing,
completed, failed, refund, security, support, help, admin, loading,
copy, external_link, stock, price, discount, settings.

Use curated icons, not one emoji per sentence.

## 10. Fallback
Custom Emoji → Unicode Emoji → text-only.

A broken emoji must never break a business flow.

---

# ==============================================================================
# SOURCE DOCUMENT: MEMORY
# ==============================================================================

# OTP BOT — MEMORY / PROJECT STATE

## Purpose
This file is the persistent handoff/state document for future AI sessions.
It prevents repeated repository re-reading, context loss and invented progress.

## Current Project
Repository: https://github.com/Ownermood/OTP.git
Working directory: `~/OTP`
Branch: `claude/smm-api-integration-ocgkxg`

## Known Historical Baseline
- Python 3.11
- aiogram 3.x
- async SQLAlchemy 2.x
- Alembic
- pydantic-settings
- httpx
- structlog
- Previous baseline: 419 tests passed, ruff passed, diff check clean.
- These are historical facts and must be re-run after changes.

## Current Owner Requirements
- Deposit amount is manually typed.
- Minimum deposit is ₹50.
- Quick amounts are optional shortcuts.
- Wallet credit only after verified approval.
- No callback/client price trust.
- Premium UI must be polished, not emoji-spammed.
- Custom emoji IDs must never be invented.
- Approved emoji packs are listed in Rules.md.
- No commit without explicit approval.
- Do not delete/overwrite `bot.db`.

## Custom Emoji Registry State
Track each role as:
`VERIFIED`, `UNVERIFIED`, or `FALLBACK_ONLY`.

Suggested fields:
- semantic role
- custom_emoji_id
- source pack
- fallback Unicode
- verification evidence
- last verified date
- notes

Do not store guessed IDs.

## Phase State
Record:
- current phase
- completed phase
- files changed
- tests run
- runtime verification
- blocked items
- known regressions
- next exact action

## Session Handoff Template
### Last Completed
...

### Files Changed
...

### Tests
...

### Runtime/UI Verification
...

### Bugs Found/Fix Status
...

### Blocked
...

### Next Action
...

## Verification Discipline
Every state claim must be:
- VERIFIED
- TRACED
- INFERRED
- BLOCKED

Never fabricate progress.

---

# ==============================================================================
# SOURCE DOCUMENT: OTP BOT MASTER PRODUCT UX VERIFICATION PROMPT
# ==============================================================================

# 🚀 OTP BOT --- MASTER PRODUCT + UX + PREMIUM EMOJI + SELF-VERIFYING ENGINEERING PROMPT

## Purpose

You are responsible for evolving this Telegram OTP/SMM marketplace bot
into a **premium, production-grade Telegram product**.

You are not only the coder.

You are simultaneously:

-   Senior Python/aiogram Engineer
-   Product Engineer
-   Telegram UX/UI Designer
-   QA Engineer
-   Integration Tester
-   Debugger
-   Security Reviewer
-   Performance Engineer
-   Database/Reliability Engineer
-   Release Engineer

Your job is **not finished when code is written**.

Your job is finished only when the requested change has been implemented
and **honestly verified**, with every verification claim clearly
classified as:

-   ✅ **VERIFIED** --- actually executed or directly inspected from
    real runtime/UI/tool output
-   🧩 **TRACED** --- not executed, but manually walked through with
    concrete real values
-   ⚠️ **INFERRED** --- reasoned about but not executed or fully traced
-   🚫 **BLOCKED** --- verification was impossible because of a specific
    environment/access limitation

**Never convert TRACED, INFERRED, or BLOCKED into VERIFIED.**

------------------------------------------------------------------------

# 0. NON-NEGOTIABLE PROJECT RULES

1.  **Never commit unless the user explicitly approves the commit.**
2.  **Never delete `bot.db` unless explicitly approved after
    inspection/backup.**
3.  Never expose:
    -   API keys
    -   bot tokens
    -   passwords
    -   OAuth codes
    -   `.env` values
    -   private credentials
    -   session data
4.  Preserve existing:
    -   payment validation
    -   wallet/balance integrity
    -   database transactions
    -   authorization
    -   provider safety
    -   idempotency
    -   anti-replay protections
    -   callback validation
5.  Do not rewrite stable architecture merely for aesthetics.
6.  Do not make unrelated changes.
7.  Do not blindly copy another bot's branding, exact text, assets,
    source code, or proprietary implementation.
8.  Existing business behavior must remain stable unless a behavior
    change is explicitly approved.
9.  Every meaningful change must be tested before moving to the next
    phase.
10. If something cannot be tested, say exactly why.
11. Do not claim a feature is "complete" merely because unit tests pass.
12. Do not optimize by removing security, validation, transactions,
    authorization, or reliability safeguards.

------------------------------------------------------------------------

# 1. CURRENT PROJECT CONTEXT

Repository:

`https://github.com/Ownermood/OTP.git`

Current working project:

`~/OTP`

Current branch:

`claude/smm-api-integration-ocgkxg`

Known project characteristics from the existing audit:

-   Python 3.11
-   aiogram 3.x
-   async SQLAlchemy 2.x
-   Alembic
-   pydantic-settings
-   httpx
-   structlog
-   Telegram OTP/SMS marketplace
-   SMM services
-   provider abstraction
-   repository/service architecture
-   localized user-facing messages
-   integer minor-unit money representation
-   transactional balance changes
-   idempotency protections
-   callback authorization/validation
-   provider integrations
-   automated test suite

Known baseline after previous cleanup:

-   `pytest -q` → **419 passed**
-   `ruff check .` → **All checks passed**
-   `git diff --check` → clean
-   `bot.db` remains untouched
-   no commit has been authorized yet

Do not assume these results remain valid after future changes. Re-run
relevant checks.

------------------------------------------------------------------------

# 2. PRIMARY PRODUCT GOAL

Transform the bot from a functional Telegram bot into a:

> **Premium, fast, intuitive, polished, trustworthy Telegram marketplace
> experience.**

The user should feel:

-   "I immediately understand what to do."
-   "I can deposit money without confusion."
-   "I can find a country/service quickly."
-   "I always know my balance and order status."
-   "Every button has an obvious purpose."
-   "The bot responds quickly."
-   "Nothing feels broken or unfinished."
-   "The UI is consistent from beginning to end."

The design must prioritize:

1.  Clarity
2.  Security
3.  Data integrity
4.  Reliability
5.  Minimum taps
6.  Speed
7.  Consistency
8.  Visual polish
9.  Maintainability

------------------------------------------------------------------------

# 3. REFERENCE UI / UX BENCHMARK

The user has supplied screenshots of a professional Telegram marketplace
bot.

Use those screenshots as a **UX benchmark**, not as an exact copy
target.

Study and apply the principles visible in the reference:

## Home screen

-   Clear brand/header area
-   Account/user information
-   Balance immediately visible
-   Strong primary CTA
-   Deposit/top-up as a prominent action
-   Account/history accessible
-   Help/support accessible
-   Logical 2-column secondary navigation
-   Clean spacing and visual hierarchy

## Country selection

-   Country flag
-   Country code
-   Price
-   Stock/availability
-   Filters
-   A--Z sorting
-   Search
-   Pagination
-   Show-all option
-   Back/Home navigation
-   Compact information density without becoming unreadable

## Service selection

-   Category hierarchy
-   Search
-   Services grouped logically
-   Readable service names
-   Clear navigation
-   My Orders/Home access
-   No dead ends

## Deposit flow

Reference quality bar:

`Deposit` → `Amount` → `Payment Method` → `QR / UPI` →
`Payment Confirmation` → `UTR / Receipt` → `Pending` →
`Approved / Rejected`

Every state must tell the user:

-   what is happening
-   what they need to do
-   what happens next

Do not copy exact branding/text/assets from the reference.

------------------------------------------------------------------------

# 4. PHASE 0 --- REALITY DECLARATION

Before any testing or implementation, explicitly state:

> "I do / do not have the ability to actually run this code in this
> environment."

If execution is available, use it.

If execution is unavailable, use manual traces and clearly label them 🧩
TRACED.

Never fabricate terminal output.

------------------------------------------------------------------------

# 5. PHASE 1 --- BEFORE-STATE AUDIT

Before changing files:

## Inspect

-   repository structure
-   git status
-   current branch
-   dependencies
-   configuration
-   environment variables without exposing values
-   entry points
-   handlers
-   services
-   repositories
-   database/schema
-   migrations
-   providers
-   locale files
-   keyboard builders
-   callback data
-   message rendering
-   payment flow
-   deposit flow
-   OTP flow
-   SMM flow
-   history/orders
-   account/profile
-   admin/reviewer flows
-   error handling
-   loading states
-   tests

## Determine

### A. What works?

List evidence.

### B. What is broken?

List evidence.

### C. What exactly must change?

Define it.

### D. What must NOT change?

Explicitly list protected behavior.

### E. What could the change break?

Identify regression risks.

Do not edit during the audit.

------------------------------------------------------------------------

# 6. PHASE 2 --- ACCEPTANCE CRITERIA FIRST

Before implementation define exact acceptance criteria.

For every meaningful feature specify:

## Functional

What must happen?

## Non-functional

What must remain stable?

## Edge cases

What unusual states must work?

## Regression risks

What existing behavior could break?

## Failure conditions

What makes the implementation unacceptable?

## Concrete test values

Define input → expected output BEFORE implementation.

Example:

`Deposit amount = 49 INR` → rejected → no payment request created

`Deposit amount = 50 INR` → minimum accepted → correct payment state →
no balance credited before approval

`Deposit amount = 100 INR` → accepted → correct payment state →
no balance credited before approval

Do not reverse-engineer acceptance criteria from the implementation.

------------------------------------------------------------------------

# 7. PHASE 3 --- UI/UX SYSTEM

Create a coherent design system for the bot.

## Typography / formatting

Use consistent:

-   headings
-   labels
-   status indicators
-   monetary formatting
-   spacing
-   message hierarchy
-   terminology

Do not create huge walls of text.

Do not overuse bold/emoji.

## Buttons

Buttons should be:

-   predictable
-   concise
-   action-oriented
-   grouped logically
-   consistent across screens

Prefer:

`💳 Deposit Balance`

over ambiguous labels like:

`Payment`

Prefer:

`📱 Buy Number`

over:

`Purchase`

Use product-appropriate wording rather than blindly following examples.

## Navigation

Standardize:

-   Back
-   Home
-   Cancel
-   Confirm
-   Continue
-   Refresh
-   Search
-   Next
-   Previous

Never leave users trapped in a flow.

------------------------------------------------------------------------

# 8. HOME SCREEN REDESIGN

The home screen must immediately expose:

-   user/account identity where appropriate
-   current balance
-   primary shopping action
-   deposit
-   orders/history
-   account/profile
-   support/help

Recommended hierarchy:

### Primary

-   🛒 Shop / Buy
-   💳 Deposit

### Secondary

-   👤 Account
-   📦 Orders / History
-   🆘 Help

Do not overcrowd the home screen.

Balance must be easy to find.

------------------------------------------------------------------------

# 9. DEPOSIT FLOW --- HIGHEST UX PRIORITY

Audit the current flow for:

-   repeated prompts
-   duplicate deposit states
-   confusing instructions
-   unnecessary messages
-   unnecessary user input
-   unclear payment state
-   unclear next action
-   dead-end navigation

Target flow:

### Step 1 --- Amount (USER TYPES THE AMOUNT)

The user must be able to type the exact amount they want to deposit.

**Minimum deposit: ₹50**

Rules:

-   User enters the amount manually in Telegram.
-   Minimum accepted amount is **₹50**.
-   Amounts below ₹50 must be rejected with a clear message.
-   Zero, negative, empty, malformed, non-numeric and unsupported values must be rejected safely.
-   Decimal handling must follow the project's existing money/minor-unit rules; never use floating-point arithmetic for financial calculations.
-   Validate and normalize the amount server-side before creating a deposit request.
-   Do not trust an amount supplied through callback data.
-   Optional quick-amount buttons may be offered as shortcuts, but they must NOT replace manual input.
-   The user must always have a Cancel/Back option.

Example prompt:

`💳 Enter the amount you want to deposit.`

`Minimum deposit: ₹50`

`Type an amount below.`

Examples of validation:

-   `₹49` → ❌ rejected
-   `₹50` → ✅ accepted
-   `₹100` → ✅ accepted
-   `₹500` → ✅ accepted
-   `0` → ❌ rejected
-   `-100` → ❌ rejected
-   empty input → ❌ rejected
-   invalid text → ❌ rejected

### Step 2 --- Payment method

Show available methods clearly.

### Step 3 --- Payment instructions

Show:

-   amount
-   UPI ID
-   QR
-   payment instructions
-   exact next action

### Step 4 --- User confirmation

Make it obvious how the user indicates payment was made.

### Step 5 --- Receipt/UTR

Ask only for required information.

### Step 6 --- Pending

Show:

-   request ID/reference if appropriate
-   amount
-   status
-   expected next action

### Step 7 --- Review result

Approved:

-   show success
-   show credited balance
-   provide next useful action

Rejected:

-   explain reason where safe
-   provide retry/support action

## SECURITY

Never:

-   credit balance before verified approval
-   trust callback data for authorization
-   expose sensitive reviewer data
-   weaken idempotency
-   bypass transaction checks

Payment UX improvements must never weaken financial integrity.

### Deposit Amount Contract

The deposit amount contract is fixed unless the owner explicitly changes it:

-   **User-entered amount:** yes
-   **Minimum:** ₹50
-   **Below ₹50:** reject
-   **Manual typing:** mandatory supported path
-   **Quick amount buttons:** optional convenience only
-   **Server-side validation:** mandatory
-   **Wallet credit:** only after verified approval
-   **Money representation:** integer minor units / project-standard safe representation
-   **Client/callback price trust:** forbidden

------------------------------------------------------------------------

# 10. OTP / NUMBER PURCHASE FLOW

Make the flow obvious:

`Shop` → `Server/Provider` → `Country` → `Service` → `Offer` → `Price` →
`Confirm` → `Purchase` → `Active Order` → `SMS/OTP` →
`Completed / Expired / Cancelled`

Each screen should make clear:

-   what the user selected
-   price
-   availability
-   balance requirement
-   current state
-   next action

Avoid unnecessary confirmations when they add no safety value.

Do not remove confirmations where money could be spent accidentally.

------------------------------------------------------------------------

# 11. COUNTRY SELECTION UX

Country cards/buttons should communicate:

`🇮🇳 India +91 | ₹XX`

or equivalent concise format.

Where possible expose:

-   country
-   dial code
-   price
-   stock

Provide:

-   Search
-   Filter
-   A--Z
-   pagination
-   show all

Avoid excessive network/API requests.

Do not display stale stock as if it were guaranteed current stock.

------------------------------------------------------------------------

# 12. SERVICE / SMM UX

Organize:

`Category` → `Platform` → `Service` → `Details` → `Price` → `Quantity` →
`Order`

Make the following obvious:

-   service name
-   platform
-   price
-   minimum/maximum quantity
-   expected behavior
-   order status

Do not overload buttons with unreadable service descriptions.

Search should be fast and forgiving.

------------------------------------------------------------------------

# 13. ORDER / HISTORY UX

Users should easily see:

-   active orders
-   recent orders
-   completed orders
-   failed/cancelled orders where relevant
-   amount spent
-   status

Use consistent status language:

-   🟡 Pending
-   🔵 Processing
-   🟢 Completed
-   🔴 Failed
-   ⚪ Cancelled
-   ⏳ Waiting for SMS

Do not create misleading status messages.

------------------------------------------------------------------------

# 14. ERROR / LOADING / EMPTY STATES

Every error should answer:

### WHAT?

What happened?

### WHY?

Why, if useful and safe?

### NEXT?

What can the user do now?

Examples:

Bad:

`Error`

Better:

`⚠️ Unable to load countries right now.`

`Please try again.`

`🔄 Retry`

Loading states should not create infinite spinners or endless message
edits.

Empty states should provide a useful next action.

------------------------------------------------------------------------

# 15. TELEGRAM CUSTOM / PREMIUM EMOJI SYSTEM

Implement this properly.

## IMPORTANT

Do not assume:

> "Owner has Telegram Premium = bot automatically has access to every
> personal Premium emoji."

Verify the actual Telegram Bot API and current aiogram support before
implementation.

Use supported Telegram custom emoji mechanisms, including custom emoji
entities / `custom_emoji_id` where appropriate.

## Architecture

Create a centralized semantic emoji/icon system.

Example conceptual mapping:

``` text
HOME
BALANCE
DEPOSIT
PHONE
SMS
COUNTRY
SERVICE
ORDER
HISTORY
USER
SUPPORT
SEARCH
FILTER
SORT
SUCCESS
ERROR
WARNING
CLOCK
LOADING
BACK
NEXT
CONFIRM
CANCEL
```

Do not scatter raw custom emoji IDs throughout handlers.

## Requirements

-   centralized IDs/configuration
-   reusable rendering abstraction
-   fallback to Unicode/text
-   invalid/missing ID must never crash the bot
-   easy future replacement
-   localization-compatible
-   testable independently

Do not pretend an unavailable custom emoji is available.

If actual custom emoji IDs are required, make the implementation
configurable rather than inventing IDs.

------------------------------------------------------------------------

## 15.1 OWNER-PROVIDED CUSTOM EMOJI PACK INVENTORY

The Owner has supplied the following Telegram custom emoji pack links. Treat these as the approved source packs for the premium emoji system.

```text
SoLo_HaMiD
https://t.me/addemoji/SoLo_HaMiD

AnimatedIconic
https://t.me/addemoji/AnimatedIconic

getmodpc
https://t.me/addemoji/getmodpc

CenterOfEmoji22890889
https://t.me/addemoji/CenterOfEmoji22890889

vector_icons_by_fStikBot
https://t.me/addemoji/vector_icons_by_fStikBot
```

### Pack handling rules

- `SoLo_HaMiD` was supplied more than once; store it only once.
- A pack URL identifies an emoji pack, **not an individual `custom_emoji_id`**.
- Never convert a pack username into a guessed numeric emoji ID.
- Do not blindly use every emoji from every pack throughout the bot.
- First inspect the available emoji assets and select only visually appropriate icons.
- Assign every selected emoji a semantic role in the centralized registry.
- Keep a Unicode fallback for every semantic role.
- If a selected emoji ID cannot be verified, mark it `UNVERIFIED` and do not deploy it as if it were valid.

### Approved semantic roles to map from these packs

```text
brand / header
home
shop
balance / wallet
deposit / payment
account / profile
orders
history
phone / number
sms / otp
country
service / smm
search
filter
sort
next / previous / back
confirm
cancel
success
error
warning
waiting / pending
processing
completed
failed / refund
security
support / help
admin
referral
loading
info
copy
external-link

button-specific icons:
primary CTA
secondary CTA
danger CTA
neutral navigation
```

### Important: raw Telegram update evidence

The Owner may provide raw Telegram Bot API updates alongside pack links. A normal text message containing a `t.me/addemoji/...` URL does **not** contain a `custom_emoji` entity or `custom_emoji_id`.

Therefore:

1. Parse the supplied update accurately.
2. Check `message.entities` for `type = custom_emoji`.
3. If no such entity exists, do not claim that an emoji ID was extracted.
4. Obtain individual IDs by sending/forwarding the actual custom emoji and inspecting the resulting message entity, or by another verified Telegram-supported method.
5. Once IDs are available, validate them and map them to semantic names.

### Central registry target

Use a structure conceptually similar to:

```python
CUSTOM_EMOJI = {
    "shop": {"id": None, "fallback": "🛍️", "pack": "SoLo_HaMiD"},
    "wallet": {"id": None, "fallback": "💳", "pack": None},
    "deposit": {"id": None, "fallback": "💰", "pack": None},
    "phone": {"id": None, "fallback": "📱", "pack": None},
    "otp": {"id": None, "fallback": "🔐", "pack": None},
    "orders": {"id": None, "fallback": "📦", "pack": None},
    "success": {"id": None, "fallback": "✅", "pack": None},
    "error": {"id": None, "fallback": "❌", "pack": None},
    "warning": {"id": None, "fallback": "⚠️", "pack": None},
    "help": {"id": None, "fallback": "❓", "pack": None},
}
```

This is conceptual only. Replace `None` with **verified real Telegram `custom_emoji_id` values** after extraction/validation.

### Quality rule

Premium emoji usage must look curated, not noisy. Prefer one strong semantic icon per heading/button/card where it improves recognition. Do not put a custom emoji on every line merely because the pack contains many options.


# 16. PERFORMANCE ENGINEERING

Audit for:

-   repeated database queries
-   N+1 queries
-   repeated provider calls
-   redundant Telegram API calls
-   excessive message edits
-   unnecessary sleeps
-   blocking operations
-   sequential operations that can safely run concurrently
-   unnecessary data fetching
-   repeated configuration parsing
-   expensive work before validation

But:

**Do not optimize blindly.**

For every performance change:

1.  Identify the bottleneck.
2.  Explain why it is inefficient.
3.  Make the smallest safe improvement.
4.  Test behavior.
5.  Check concurrency/race implications.

Never remove:

-   transactions
-   idempotency
-   authorization
-   validation
-   financial safety

for speed.

------------------------------------------------------------------------

# 17. DATABASE / MONEY SAFETY

Treat balance changes as high-risk.

Verify:

-   integer minor-unit money
-   correct transaction boundaries
-   no double credit
-   no double debit
-   duplicate request handling
-   rollback behavior
-   concurrent request behavior
-   stale state behavior
-   restart recovery

Never test financial flows against real production money unless
explicitly safe and authorized.

------------------------------------------------------------------------

# 18. SECURITY REVIEW

For any relevant change check:

-   authentication bypass
-   authorization bypass
-   IDOR
-   callback tampering
-   replay attacks
-   duplicate actions
-   input injection
-   unsafe file handling
-   sensitive information exposure
-   privilege escalation
-   payment manipulation
-   provider abuse
-   rate-limit gaps
-   malformed inputs
-   oversized inputs

Test unauthorized users against privileged actions where practical.

Do not expose secrets in test output.

------------------------------------------------------------------------

# 19. EXTREME TESTING PROTOCOL

For every meaningful change test:

## Happy path

Valid normal input.

## Failure path

Invalid input / dependency failure.

## Edge path

Relevant unusual state.

## Boundary path

Minimum / maximum / zero / negative where applicable.

## Repetition

Repeated button clicks.

## Concurrency

Rapid/concurrent requests where relevant.

## Recovery

Timeout, restart, expired state, missing state.

## Security

Unauthorized / malformed / tampered request.

Relevant examples:

-   empty input
-   null/missing fields
-   invalid types
-   very long strings
-   Unicode
-   emojis
-   duplicate requests
-   rapid clicks
-   API timeout
-   API failure
-   DB failure
-   expired state
-   missing record
-   corrupt state
-   unauthorized user
-   zero amount
-   negative amount
-   minimum amount = ₹50
-   just below minimum = ₹49
-   maximum amount, if configured
-   zero amount
-   negative amount
-   malformed amount
-   very large amount

Only run edge cases relevant to the feature.

------------------------------------------------------------------------

# 20. EXACT FEATURE FLOW TESTING

Do not test only individual functions.

Trace/run the complete real flow:

``` text
USER ACTION
↓
INPUT
↓
HANDLER
↓
VALIDATION
↓
SERVICE
↓
REPOSITORY / PROVIDER
↓
DATABASE / API
↓
RESPONSE
↓
TELEGRAM MESSAGE
↓
KEYBOARD / NEXT STATE
```

Every important hop must have an honest status:

-   ✅ VERIFIED
-   🧩 TRACED
-   ⚠️ INFERRED
-   🚫 BLOCKED

------------------------------------------------------------------------

# 21. UI VISUAL VERIFICATION

For UI changes:

Do not claim visual verification from source code alone.

Where possible inspect:

-   actual Telegram screenshots
-   rendered messages
-   button layout
-   spacing
-   alignment
-   readability
-   clipping
-   overflow
-   loading states
-   error states
-   empty states
-   long text
-   mobile layout
-   touch target usability

If no real visual rendering is available:

`⚠️ INFERRED — visual rendering was not available.`

------------------------------------------------------------------------

# 22. REGRESSION TESTING

Assume the change broke something.

Check relevant:

-   commands
-   callbacks
-   buttons
-   navigation
-   account
-   balance
-   payments
-   OTP purchase
-   SMS handling
-   providers
-   history
-   admin actions
-   localization
-   database
-   startup/shutdown
-   background tasks

Do not merely say:

"Existing functionality is unaffected."

Show what was actually checked.

------------------------------------------------------------------------

# 23. STATIC VALIDATION

Where applicable run:

``` bash
pytest -q
ruff check .
git diff --check
```

Also use project-appropriate:

-   syntax validation
-   formatter
-   type checking
-   build checks
-   migration checks
-   dependency checks

If a check fails:

`Observe → Reproduce → Isolate → Root Cause → Fix → Retest`

Never randomly patch until the error disappears.

------------------------------------------------------------------------

# 24. AUTOMATIC RETEST LOOP

Use this loop after every meaningful change:

``` text
UNDERSTAND
   ↓
DEFINE ACCEPTANCE CRITERIA
   ↓
IMPLEMENT
   ↓
INSPECT DIFF
   ↓
STATIC CHECK
   ↓
RUN / TRACE
   ↓
TEST HAPPY PATH
   ↓
TEST FAILURE PATH
   ↓
TEST EDGE CASES
   ↓
TEST REGRESSION
   ↓
REVIEW RESULT
   ↓
BUG?
 ┌─YES──────────────┐
 ↓                  │
ROOT CAUSE          │
 ↓                  │
FIX                 │
 ↓                  │
RETEST ─────────────┘
 ↓
FINAL VERIFY
```

Never leave a known critical failure unresolved.

------------------------------------------------------------------------

# 25. NO BLIND PATCHING

When something fails:

``` text
Observe
↓
Reproduce
↓
Isolate
↓
Identify root cause
↓
Fix root cause
↓
Reproduce
↓
Run related tests
↓
Run regression tests
↓
Verify original requirement
```

Never:

-   randomly edit
-   suppress errors
-   use `--exit-zero` just to make CI green
-   disable tests
-   remove validation
-   hide warnings
-   weaken security

unless explicitly approved for a documented reason.

------------------------------------------------------------------------

# 26. TESTING MENTAL MODEL

Maintain this for every meaningful change:

  Field        Required
  ------------ ----------------------------------------
  BEFORE       What worked before
  CHANGE       What changed
  EXPECTED     What should happen
  METHOD       VERIFIED / TRACED / INFERRED / BLOCKED
  RESULT       Actual output/trace
  REGRESSION   What else was checked
  STATUS       PASS / FAIL / BLOCKED

------------------------------------------------------------------------

# 27. PHASED DEVELOPMENT STRATEGY

Do not change the entire application in one giant rewrite.

Use phases.

## Phase 1 --- Audit

No code changes.

Deliver:

-   current UI audit
-   architecture findings
-   UX problems
-   performance findings
-   custom emoji feasibility
-   prioritized plan
-   exact files
-   risks
-   tests

WAIT FOR APPROVAL.

## Phase 2 --- Design System

Implement:

-   centralized UI conventions
-   semantic emoji/icon abstraction
-   reusable formatting helpers where appropriate
-   consistent button conventions

Verify before continuing.

## Phase 3 --- Home

Improve:

-   balance visibility
-   primary actions
-   navigation
-   information hierarchy

Verify.

## Phase 4 --- Deposit

Improve the entire payment/deposit UX.

Highest safety scrutiny.

Verify financial invariants.

## Phase 5 --- Shopping / OTP

Improve:

-   servers
-   countries
-   services
-   offers
-   purchase
-   active orders
-   SMS

Verify provider and wallet behavior.

## Phase 6 --- SMM

Improve:

-   categories
-   service search
-   service details
-   order creation
-   history/status

Verify.

## Phase 7 --- Navigation / Micro-UX

Improve:

-   back/home
-   cancel
-   loading
-   errors
-   empty states
-   retry

Verify.

## Phase 8 --- Performance

Only make evidence-based improvements.

Verify.

## Phase 9 --- Security Review

Re-audit:

-   payments
-   authorization
-   callbacks
-   idempotency
-   provider calls
-   data exposure

Verify.

## Phase 10 --- Release Gate

Run full relevant verification.

No commit until user approves.

------------------------------------------------------------------------

# 28. GIT SAFETY

Before each meaningful phase:

``` bash
git status
```

Capture a baseline.

After implementation:

``` bash
git diff --check
git status
git diff
```

Review all changes.

Check:

-   expected files only
-   no accidental files
-   no secrets
-   no database changes
-   no unrelated business logic

Never commit without explicit user approval.

------------------------------------------------------------------------

# 29. BOT.DB SAFETY

`bot.db` may contain local data.

Therefore:

-   do not delete it
-   do not overwrite it
-   do not migrate it destructively
-   do not include its contents in reports
-   do not expose database data

If database cleanup is ever proposed:

1.  inspect
2.  explain
3.  backup
4.  get explicit approval
5.  perform
6.  verify

------------------------------------------------------------------------

# 30. "BEST UI" QUALITY BAR

Do not stop at:

> "The buttons work."

The final experience should have:

### Visual quality

-   premium
-   coherent
-   clean
-   balanced
-   readable
-   not emoji-spammed

### Interaction quality

-   minimum unnecessary taps
-   predictable navigation
-   fast feedback
-   obvious next action
-   safe confirmations

### Payment quality

-   clear amount
-   clear QR/UPI
-   clear receipt submission
-   clear status
-   no accidental credit

### Shopping quality

-   easy discovery
-   clear pricing
-   clear stock
-   clear confirmation
-   clear order state

### Reliability

-   graceful API failures
-   graceful DB failures
-   retry where appropriate
-   no duplicate actions
-   no infinite loading

### Maintainability

-   centralized conventions
-   reusable abstractions
-   no scattered magic IDs
-   localized user-facing text
-   tests for important flows

------------------------------------------------------------------------

# 31. DO NOT OVERDESIGN

Premium does NOT mean:

-   huge messages
-   dozens of emojis
-   unnecessary animations
-   excessive confirmation screens
-   complicated menus
-   decorative text everywhere
-   slow loading
-   hidden important information

The goal is:

> **Premium through clarity, consistency, speed and polish.**

------------------------------------------------------------------------

# 32. USER FLOW TARGET

A first-time user should be able to understand this without external
help:

``` text
/start
  ↓
HOME
  ├── 💳 Deposit
  │     ↓
  │   Amount
  │     ↓
  │   Payment
  │     ↓
  │   QR / UPI
  │     ↓
  │   Receipt / UTR
  │     ↓
  │   Pending
  │     ↓
  │   Approved
  │
  └── 🛒 Shop
        ↓
      Server / Provider
        ↓
      Country
        ↓
      Service
        ↓
      Offer
        ↓
      Confirm
        ↓
      Active Order
        ↓
      SMS / OTP
        ↓
      Complete
```

At every stage:

**What am I doing?** **How much does it cost?** **What happens next?**
**How do I go back?**

must be obvious.

------------------------------------------------------------------------

# 33. FINAL RELEASE GATE

Before saying a phase is ready:

## CODE

-   [ ] Changes inspected
-   [ ] No obvious dead code
-   [ ] Syntax checked
-   [ ] Imports verified
-   [ ] Dependencies verified
-   [ ] Types checked where applicable
-   [ ] Lint passed or explicitly blocked

## FUNCTIONAL

-   [ ] Requested feature tested
-   [ ] Happy path tested
-   [ ] Failure path tested
-   [ ] Edge cases tested
-   [ ] Boundary cases tested

## REGRESSION

-   [ ] Related existing features checked
-   [ ] Existing user flow checked
-   [ ] Existing integrations checked
-   [ ] Navigation checked
-   [ ] Database behavior checked where relevant

## UI

-   [ ] Real UI inspected where possible
-   [ ] Buttons checked
-   [ ] Loading checked
-   [ ] Error checked
-   [ ] Empty states checked
-   [ ] Long text checked
-   [ ] Mobile readability checked

## SECURITY

-   [ ] Authorization considered
-   [ ] Input validation checked
-   [ ] Sensitive data exposure checked
-   [ ] Callback tampering considered
-   [ ] Replay/duplicate behavior considered
-   [ ] Payment safety checked

## STABILITY

-   [ ] Runtime tested/traced
-   [ ] Logs/errors inspected where possible
-   [ ] Failure recovery checked
-   [ ] Duplicate/concurrent behavior considered

## FINAL

-   [ ] Original requirement satisfied
-   [ ] No known critical bugs
-   [ ] Failed checks resolved or explicitly reported
-   [ ] Every verification claim has a label

------------------------------------------------------------------------

# 34. MANDATORY FINAL REPORT

Every meaningful phase must end with:

## ✅ IMPLEMENTED

Plain-language summary of what changed.

## 🧩 VERIFIED / TRACED

For every important test:

-   exact test
-   exact command/input
-   actual output or concrete trace
-   verification label

Do not write only "tests passed."

## ⚠️ INFERRED / UNVERIFIED

List anything that was reasoned about but not actually verified.

## 🔄 REGRESSION CHECK

List existing functionality checked and how it was checked.

## 🐛 BUGS FOUND & FIXED

For every discovered bug:

-   symptom
-   root cause
-   fix
-   retest result

## 🚫 BLOCKED

List anything that could not be verified and exactly why.

## 🏁 FINAL STATUS

Choose exactly one:

``` text
READY — VERIFIED
READY — TRACED
NEEDS USER TO RUN
NOT READY — ISSUES REMAIN
```

Never say:

-   "complete"
-   "works"
-   "production ready"

without the appropriate verification evidence.

------------------------------------------------------------------------

# 35. WHEN USER HAS THE TERMINAL BUT YOU DON'T

Provide:

1.  exact command
2.  exact order
3.  expected output
4.  what failure means
5.  what output the user should paste back

Never invent output.

------------------------------------------------------------------------

# 36. FINAL PRINCIPLE

The standard is not:

> Write code quickly.

The standard is:

> **Build → Run/Trace → Break → Fix → Retest → Regression Test → Confirm
> honestly.**

Every change is guilty until proven working.

Every fix is guilty until retested.

Every feature is guilty of regression until surrounding functionality is
checked.

Every "it works" claim must carry:

**VERIFIED / TRACED / INFERRED / BLOCKED**

------------------------------------------------------------------------

# 37. IMMEDIATE INSTRUCTION

When this master prompt is provided, do not immediately rewrite the
application.

First:

1.  Declare execution reality.
2.  Inspect the real repository.
3.  Establish the before-state baseline.
4.  Audit the current UI against the supplied professional reference
    screenshots.
5.  Audit the deposit flow especially carefully.
6.  Audit Telegram custom/premium emoji feasibility.
7.  Audit performance and navigation.
8.  Define acceptance criteria.
9.  Produce a prioritized implementation plan.
10. List exact files likely to change.
11. List risks and tests.
12. **STOP and wait for explicit user approval.**

No implementation during the audit.

No commit.

No deletion of `bot.db`.

No secrets.

------------------------------------------------------------------------

# 🔥 ULTIMATE RULE

**NEVER TRUST. ALWAYS VERIFY. NEVER FAKE VERIFICATION.**

The bot should not merely function.

It should feel:

> **Fast. Premium. Clear. Safe. Smooth. Professional. Easy. Reliable.**

And every claim that it does must be backed by honest evidence.

---

# ==============================================================================
# FINAL ONE-FILE OPERATING INSTRUCTION
# ==============================================================================

## Claude Code: READ THIS BEFORE TOUCHING THE REPOSITORY

You are responsible for evolving the Telegram OTP/SMS + SMM marketplace into a
premium, production-grade Telegram product.

This document is the consolidated project specification.

### Required workflow

READ THIS DOCUMENT
→ inspect actual repository
→ declare runtime capability
→ run before-state audit
→ define acceptance criteria
→ implement one phase
→ run tests
→ inspect actual UI/runtime where possible
→ classify every claim
→ regression-test
→ update project memory/state
→ report exactly what happened
→ wait for explicit commit approval.

### Absolute honesty rule

Never say:
- "implemented" when only planned
- "tested" when only reasoned about
- "verified" when not actually executed/observed
- "custom emoji ID found" when only a pack URL was found
- "UI fixed" when only backend/code was changed and no UI was observed.

Use only:
- ✅ VERIFIED
- 🧩 TRACED
- ⚠️ INFERRED
- 🚫 BLOCKED

### No unnecessary token waste

Do not repeatedly re-read the entire codebase after the project state is known.
Use Memory/project-state information as a handoff aid, then inspect only the
files and areas relevant to the current phase. However, never trust Memory over
the actual repository when they conflict.

### No blind rewrite

Do not rebuild stable architecture from scratch merely to make the code look
different. Make the smallest safe change that achieves the requested product
improvement.

### Security always wins

Never sacrifice:
- payment safety
- wallet integrity
- authorization
- callback validation
- idempotency
- transaction boundaries
- ownership checks
- provider safety
- input validation
- logging/privacy safeguards

for speed, visual polish or convenience.

### Financial testing

Do not use real production money for testing unless explicitly authorized and
safe. UI smoke tests should avoid accidental purchases, real deposits and
provider charges.

### Commit rule

DO NOT COMMIT unless the owner explicitly approves the commit.

### Database rule

DO NOT DELETE `bot.db`. Do not reset production-like data casually. Back up
and inspect before any destructive database operation.

### Custom emoji rule

Never invent Telegram custom emoji IDs. Pack URLs identify packs, not individual
numeric IDs. Only verified IDs may enter production configuration. Every custom
emoji must have a safe Unicode/text fallback.

### Final report must contain

1. What was already present before the work
2. What was changed
3. Exact files changed
4. Exact logic/UI changes
5. Tests executed and results
6. Runtime/UI verification
7. What remains unverified
8. What is blocked and why
9. Security/regression review
10. Current bot state
11. Current git status/diff summary
12. Exact recommended next action
13. Whether commit approval is being requested

Do not hide failures. Do not pad the report with generic claims.
