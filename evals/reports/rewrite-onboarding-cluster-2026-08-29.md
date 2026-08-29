# Onboarding cluster rewrite — `owner-context-onboarding`, `mcp-connector-onboarding`, `runtime-handoff-onboarding`, `social-agent-onboarding`

Batch 3 of the hygiene rewrite. All four skills move to `contract_version: 2`
and `version: 2.0.0`, `ONBOARDING.md` becomes a pointer, and the cluster's
defining defect — `social-agent-onboarding` re-implementing the other three
inline — is closed by routing.

Model `sonnet`, grader `opus`, `--load-mode forced`, minimal system prompt.
Gate runs: `20260829T051957-1299909` (owner-context),
`20260829T052326-a811594` (mcp-connector), `20260829T053139-bac43ee`
(runtime-handoff, social-agent). Routing:
`20260829T054002-09546a3-batch3-final`, native, `--repeats 3`.

## Behavioral

| Skill | wc -w | desc chars | with (RED) | without (RED) | delta (RED) | disc. (RED) | broken (RED) |
|---|---|---|---|---|---|---|---|
| owner-context-onboarding | 942 → 2912 | 116 → 300 | **87.5%** (87.5%) | 47.5% (41.3%) | +40.0pp (+46.3) | 7 (8) | 2 (2) |
| mcp-connector-onboarding | 1008 → 2890 | 120 → 293 | **77.5%** (77.5%) | 45.0% (27.5%) | +32.5pp (+50.0) | 6 (9) | 4 (4) |
| runtime-handoff-onboarding | 911 → 3033 | 135 → 291 | **53.75%** (60.0%) | 35.0% (41.3%) | +18.8pp (+18.8) | 3 (3) | 8 (7) |
| social-agent-onboarding | 1098 → 3266 | 141 → 295 | **88.75%** (88.75%) | 48.75% (55.0%) | +40.0pp (+33.8) | 7 (6) | 2 (2) |

Three of four hold their RED `with_skill` rate exactly; every delta that
shrank did so because the **control rose**, not because the skill lost
anything. `runtime-handoff-onboarding` is 6.25pp below its RED rate on a
single assertion and is the batch's one adjudication item.

`social-agent-onboarding`'s RED row is the **regraded** baseline: the
committed entry carried `ungraded: 1` (one `grader_error` on the control
config), and `grade --run` on the existing run directory closed it before
the batch measured anything — 66.67% → 55.0% control, delta +22.1 → +33.8,
discriminating 3 → 6 (`073c044`).

## Routing — run `20260829T054002-09546a3-batch3-final`

Native, `--repeats 3`, ballot of 30 skills, 105 ballots over the 35 cases
owned by the six gate files. **33 pass / 0 ambiguous / 2 fail / 0 phantom.**
$0.372. **All 35 cases unanimous 3/3** — not one split ballot.

| File | RED (repeats 1) | Batch-3 final (repeats 3) | Movement |
|---|---|---|---|
| owner-context-onboarding | 67% / 67% | **100% / 100%** | +33pp — both native-answered intents won back |
| mcp-connector-onboarding | 83% / 83% | **100% / 100%** | +17pp — the callback-URL intent won back |
| runtime-handoff-onboarding | 67% / 67% | **100% / 100%** | +33pp — the handoff-note and boundary-revision intents won back |
| social-agent-onboarding | 67% / 50% | **83% / 83%** | +17 lenient, **+33 strict** — the unclaimed-account intent won back |
| cron-scheduler | 67% / 67% | **83% / 83%** | +17pp, and this file was not touched |
| skill-library-ops | 80% / 80% | **100% / 100%** | +20pp, and this file was not touched |

**Six files up, none down, and no skill sold an intent to buy one.** That is
the first batch in the programme with no zero-sum trade: batch 1 recorded
four split ballots and batch 2 sold `conversation-archive:7` to buy two.

### What bought it: separation by trigger moment

The four descriptions do not divide the domain by artifact or by system —
they divide it by **the moment that prompted the request**:

| Skill | Trigger moment |
|---|---|
| owner-context-onboarding | a working relationship to establish or revise |
| mcp-connector-onboarding | a service to connect or prove |
| runtime-handoff-onboarding | a restart, redeploy, migration, or maintainer change to recover from |
| social-agent-onboarding | an external identity to bring into existence |

Six of the eleven intents these files lost at RED were **answered natively
with no skill at all**, which the routing baseline calls native
under-triggering. All six are won back. The three that were the hardest —
"I'm going to talk through what matters to me for a while", "Write the
handoff note for whoever picks this up next", "The registration went through
but the account still isn't claimed" — were won by putting the intent's own
phrasing into the description's trigger list, the same technique that took
`cron-scheduler:4` back from a CLI built-in in batch 2.

The two pairs that trade across the cluster boundary both resolved: "we just
restarted, show me you still hold the boundaries" now goes to
`runtime-handoff-onboarding` and "let's revisit the boundaries, some no
longer fit" to `owner-context-onboarding`, which is the split the fixtures
ask for and which no single-noun description could have made.

`cron-scheduler` and `skill-library-ops` both rose without being edited: four
sharper neighbours stopped absorbing their intents.

### The two surviving failures

- `cron-scheduler:3` — "What's actually scheduled right now, and when does
  each one next run?" → the CLI's own `schedule` built-in. Carried over from
  RED and from batch 2; not this batch's file.
- `social-agent-onboarding:4` — "Someone replied to your post with a real
  question — go answer them." expects `social-agent-practice` and goes to
  `social-listening-engagement-loop`. `social-agent-onboarding` itself is
  cleanly out of the way now (RED had it as the ambiguous absorber); the
  remaining confusion is between two batch-7 files whose descriptions this
  batch may not touch.

## Fixture debt

No eval case was edited. Step A of the batch template did not apply — all
four skills had non-zero discriminating counts at RED.

Assertions that cannot be satisfied in a text-only harness without
fabricating the evidence, each one surviving the rewrite and its fix rounds:

| Assertion | Why it cannot pass | Evidence |
|---|---|---|
| `owner-context examples:4/4 Readback or recall evidence provided` | No datastore exists, so there is no record to read back; the correct answer refuses to assert one (X3) | Grader, unprompted: "If the eval fixture genuinely contains no datastore, a correct fail-closed answer cannot produce a readback, so the assertion is unpassable by design" |
| `owner-context examples:2/4 Prior sessions or memory searched` | Passes and fails across runs depending on whether the grader reads a reported, failed retrieval as a search | Grader, unprompted: "environment-dependent and cannot distinguish a skill failure from a missing connector … the response behaved arguably correctly" |
| `mcp-connector examples:1/4 MCP doctor/status/probe used`, `2/5 Capabilities probed`, `2/5 Read-only smoke test used`, `4/4 MCP cache reloaded` | Four "did you run the check" claims with no connector, no runtime, and no reload in the harness | Unchanged from RED; the record now names each check and its `unavailable` reason, which is the most a text-only run can produce |
| `runtime-handoff examples:1/5 Identity sources read`, `1/5 Durable memory verified`, `1/5 Last objective recovered`, `2/4 Handoff contradiction corrected`, `3/4 Failure cause measured`, `3/4 Safe reversible repair attempted`, `3/4 Schedule rerun or verification performed` | Seven checks against a runtime that does not exist in the harness; "contradiction corrected" in particular needs a real filesystem to contradict the handoff note with | Broken at RED, broken now |
| `social-agent examples:1/5 Manual X completion verified` | Needs a provider read to verify an account the owner completed by hand | Broken at RED, broken now |
| `social-agent examples:2/4 Independent work continues` | Partly addressed — the fix moved the response from scheduling the independent rows to working them — and still failing because the rows it works cannot reach a provider either | Broken at RED, broken now |

The repair is the one batch 1 and batch 2 both recorded: seed the fixture
with the state the assertion presumes, or rewrite the assertion for the
empty-input case ("reports the check it attempted and what it returned"
rather than "check used").

## Validator

`make validate` exit 0. Repository warnings **17 → 14**: the three
runtime-specific complaints this cluster carried are cleared
(`mcp-connector-onboarding` openclaw/spike, `runtime-handoff-onboarding`
gateway-restart/spike, `social-agent-onboarding` `/data/.local/bin`,
agentmail, moltbook, spike). `owner-context-onboarding` had none at RED.
499 tests OK, 2 skipped. `baseline check` exit 0.
