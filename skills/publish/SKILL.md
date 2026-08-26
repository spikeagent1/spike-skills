---
name: "publish"
description: "Separate local rendering from authorized, verified external publication and revocation."
mutating: true
---

# Publish

Create a sanitized share artifact without confusing a local render with external publication.

## Effect states
Treat these as separate states: PREVIEWED, RENDERED, UPLOADED_UNVERIFIED, PUBLISHED_VERIFIED, LINK_DELIVERED, and ORIGIN_REMOVED. Never collapse an earlier state into a later one.

## Authorization envelope
Before each effect, resolve the source and version; included sections and redactions; local output path and overwrite permission; encryption choice; destination account, object path, visibility, audience, and expiry; authorized URL-delivery channel; and a separately authorized password channel.

A request for a shareable page authorizes an encrypted local render only. It does not authorize upload, public visibility, messaging, or distribution. An external release request authorizes only the named destination and audience. Public or unencrypted publication requires explicit language such as "public", "open", or "no password".

## Privacy preflight
Treat deterministic stripping as a candidate sanitizer, not proof of safety. Inspect the rendered candidate and every URL for credentials, access tokens, private query parameters, personal data, confirmation identifiers, internal paths, frontmatter, timelines, hidden content, and embedded remote resources. Redact or exclude sensitive material before any external write. Summarize material redactions without echoing sensitive values.

Never include a password in logs, filenames, the normal completion response, or the same delivery channel as the URL. If no separately authorized channel exists, return the encrypted artifact and state that password delivery remains pending.

## Render
Default to password-protected output unless the user explicitly requests public or unencrypted output. Write to a unique path unless update or overwrite was explicitly authorized. Restrict local permissions where supported and remove plaintext temporary artifacts.

Verify that the file exists and is non-empty; intended sampled content appears; prohibited markers and sampled sensitive strings do not appear; encrypted output does not contain the plaintext payload; and decryption succeeds when a password is used. A successful local render is RENDERED, not published.

## External release
Before upload, read the destination account and existing object metadata. Use a stable operation key based on source hash, destination, visibility, and expiry. An identical retry is a no-op. Changed content must not overwrite an existing object without update authority. Never infer a destination, account, recipient, or credential.

After upload, read back authoritative metadata and, where possible, test the URL as the intended audience. Verify object identity, access policy, expiry, encryption expectation, and absence of sampled prohibited content. If verification fails, report the exact partial state and preserve a safe retry key; do not invent a URL or claim publication.

Delivery is a separate mutation. Send the URL only to the authorized recipient/channel and use its own idempotency key. Deliver a password only through a different authorized channel.

## Revoke or update
Update only the verified object identity and preserve or explicitly change its access policy and expiry. Revoke only after explicit authorization, then verify origin access is gone. Explain that downloaded or cached copies and previously disclosed passwords cannot be recalled. Rotate the URL or password and republish when broader invalidation is required.

## Completion report
Report source version, local artifact, external destination, visibility, expiry, effect state, verification evidence, retry/rollback state, and pending password delivery. Never print the password.

## Operational failure conditions
Fail review if the workflow marks itself non-mutating; uploads or messages from a render-only request; prints a password; treats a pattern scrub as privacy proof; silently overwrites content; duplicates an object or message on retry; claims publication without readback; or overclaims revocation.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.

## When to use
Use this skill to publish, send, schedule, update, or otherwise mutate an external or public surface after content and authority are clear.

## When not to use
Do not use it for drafting alone, unclear targets, hidden automation, approving proposals, merging PRs, or publishing content whose claims/privacy have not been reviewed.

## Required inputs
Required inputs are exact target surface/account, content or artifact, operation, authority, review status, and rollback or correction path. If target or authority is unclear, stop with a preview request.

## Optional inputs
Optional inputs include schedule time, alt text, link preview, tags, audience, notification preference, and post-publication monitoring. Missing optional inputs default to no scheduling and no extra metadata.

## Workflow
1. Verify target, account identity, content, and current governance/review state.
2. Check privacy, factual claims, links, media, and platform constraints.
3. Present exact mutation preview and require explicit authorization unless already granted for the exact operation.
4. Execute the minimum mutation through the authorized connector.
5. Read back or verify terminal success; do not infer from request submission alone.
6. Report URL/ID, timestamp, account, verification status, and rollback/correction path.

## Sources and freshness
Use current target/account state and platform documentation for limits that affect publication. Re-check PR/CI/release state immediately before publishing claims about repository status.

## Privacy and mutations
This is a mutating skill. It may post, send, schedule, edit, delete, or update only the named target after authorization. Never expose credentials or private source material in content or logs.

## Safety boundaries
Refuse spam, undisclosed automation, private-data disclosure, impersonation, fabricated claims, unauthorized publication, or destructive edits/deletes without a clear rollback plan.

## Output contract
Return operation, target/account, content digest or title, URL/ID when available, verification result, timestamp, rollback/correction path, and any unresolved monitoring needs.

## Failure conditions
Fail when authorization is missing, target cannot be verified, connector readback fails, content violates safety/privacy, platform rejects the operation, or the result URL/ID cannot be obtained when required.

## Worked example
For "publish this wall post," preview the exact wall text and account, ask for approval, post only after approval, then return the wall URL and verification readback.
