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

## Failure conditions
Fail review if the workflow marks itself non-mutating; uploads or messages from a render-only request; prints a password; treats a pattern scrub as privacy proof; silently overwrites content; duplicates an object or message on retry; claims publication without readback; or overclaims revocation.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.
