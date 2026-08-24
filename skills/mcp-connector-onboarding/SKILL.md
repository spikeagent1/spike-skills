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
