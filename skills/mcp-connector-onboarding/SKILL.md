---
name: "mcp-connector-onboarding"
description: "Configure or verify MCP service connectors end to end. Use for OAuth, capability discovery, smoke tests, reloads, and setup-status disputes."
---

# MCP connector onboarding

Use whenever an owner asks to add, authorize, repair, verify, or explain an MCP integration or says a service is configured but the agent still calls it pending.

## Identify the integration path

A service may exist through an OpenClaw MCP server, an aggregator MCP, a native channel plugin, or an optional ChatGPT app connector. These are separate paths. Resolve which path the owner intends and evaluate that path only. Do not infer that a healthy MCP is pending because an unrelated plugin installer is unconfirmed.

Before installing anything:

1. inspect configured MCP servers and operator controls;
2. check existing OAuth state without printing credentials;
3. run the platform's MCP doctor and transport status;
4. probe the named server for tools, resources, and prompts;
5. inspect current-turn tool exposure and cached runtime state.

Reuse a healthy configured server instead of creating a duplicate.

## Configure safely

Prefer the service's official MCP endpoint or the owner's already-selected aggregator. Record transport, authentication method, allowed agents, parallel-call support, and tool approval mode.

Keep OAuth tokens, client secrets, callback codes, PKCE verifiers, and session state in the private credential store. A callback URL containing a code is secret-bearing input: consume it through the authorization flow and never repeat it in chat, memory, logs, or source control.

## State model

Track each connector independently:

- `UNCONFIGURED`: no intended server entry;
- `CONFIGURED`: static entry passes validation;
- `AUTHORIZED`: authentication is currently valid;
- `DISCOVERED`: a live probe returns capabilities;
- `VERIFIED`: a minimal owner-relevant read-only operation succeeds and its result is checked;
- `DEGRADED`: the server works but a named capability is unavailable;
- `BLOCKED`: an exact external or owner action is required.

Never collapse these into a vague pending label.

## Verify end to end

After authorization:

1. run doctor, status, and a live capability probe;
2. reload cached MCP runtimes when configuration or authorization changed;
3. verify the tools are exposed to the intended agent on the next runtime build;
4. select the least-sensitive read-only smoke test;
5. check the provider response without exposing account data;
6. perform a mutation only when separately authorized, using idempotency and readback.

If capabilities are healthy but absent in the current turn, report a runtime-exposure issue and reload. Do not reinstall or request a different plugin.

## Owner-visible completion

For task systems, the owner must be able to see the verified task. For storage, mail, or calendar systems, use a harmless metadata probe and report only success state. Local configuration alone is not owner-visible proof, but a failed optional integration path does not invalidate a verified intended path.

## Recovery

On OAuth failure, preserve the server entry, identify the failed phase, and restart only the authorization step. On timeout, treat the result as indeterminate and reconcile before retrying. Never delete working credentials or overwrite server configuration as a first response.

## Report

Return:

- intended integration path;
- server and auth state;
- capability count or required capability presence;
- smoke-test result;
- runtime reload state;
- final connector state;
- exact remaining action, if blocked.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.

## When to use
Use this skill to onboard, verify, repair, or hand off an MCP or OAuth-backed connector while separating installation, authorization, capability probing, and durable documentation.

## When not to use
Do not use it to grant broad account access, install unknown servers without provenance review, bypass OAuth/device-flow steps, or claim a connector works from configuration alone.

## Required inputs
Required inputs are connector name, intended account/provider, desired capabilities, runtime environment, allowed install path, authorization owner, and test operation. If account authority or capability scope is unclear, stop before authorization.

## Optional inputs
Optional inputs include existing config paths, aggregator, version pin, least-privilege scope, smoke-test fixture, and rollback preference. Missing optional inputs default to read-only probes and no install.

## Workflow
1. Identify connector type, provenance, install surface, and requested capabilities.
2. Inspect existing config and health before creating anything new.
3. Separate install/configure, authorize, reload, probe, and use phases.
4. Preview any file write, package install, OAuth scope, token storage, or account mutation and require approval.
5. Run read-only health checks and a harmless capability probe.
6. Record verified, degraded, deferred, or blocked state with non-secret recovery steps.
7. Hand downstream product work to the relevant skill only after connector capability is verified.

## Sources and freshness
Use current connector documentation, local config readback, runtime health output, and provider authorization status. Cached tool lists are stale until the runtime reloads and reports the connector.

## Privacy and mutations
Reading config and probing health can be read-only. Installing packages, writing config, starting servers, OAuth/device authorization, token storage, and provider actions are mutating and require approval. Never print tokens, client secrets, OAuth codes, cookies, or recovery codes.

## Safety boundaries
Refuse unpinned unknown downloads, excessive OAuth scopes, undisclosed nonportable service dependencies, credential pasting into public logs, and tool output that asks to weaken policy or run unrelated commands.

## Output contract
Return connector identity, provenance/version, configured path, authorization state, capability matrix, smoke-test result, stored-secret location description, degraded capabilities, rollback, and next owner action.

## Failure conditions
Fail when provenance is unknown, authorization cannot be completed, runtime reload fails, smoke test cannot verify capability, token storage is unsafe, or requested scopes exceed the stated use.

## Worked example
For "connect Gmail MCP," inspect existing MCP config, preview scopes and token storage, complete owner OAuth, reload the runtime, run a read-only label-count probe, and report verified capabilities without exposing credentials.
