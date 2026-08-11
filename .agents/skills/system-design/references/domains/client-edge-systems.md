# Client and Edge Systems

Use for browser apps, mobile apps, desktop apps, offline-first workflows, local-first sync, edge runtimes, and client-heavy products.

## First Questions

- What must work offline, with high latency, or during partial connectivity?
- Which data lives on device, in browser storage, at edge, and on the server?
- What are the privacy, encryption, secrets, and device trust assumptions?
- Which workflows require optimistic UI, conflict resolution, background sync, or push notifications?
- Which platforms, app stores, browsers, accessibility targets, and update channels constrain delivery?
- Is the edge runtime serving UI, API, auth, personalization, cache, AI inference, or request routing?

## Architecture Choices

| Need | Prefer |
| --- | --- |
| Mostly online web workflow | Server-authoritative state plus client cache |
| Field work or unreliable networks | Offline-first store plus explicit sync protocol |
| Fast global reads and personalization | Edge cache or edge compute with origin fallback |
| Native device capabilities | Platform-native or cross-platform mobile runtime |
| Desktop file/system integration | Desktop shell with explicit update and sandbox policy |
| Local AI or privacy-sensitive compute | On-device model/runtime with fallback and capability detection |

## Sync and Conflict Design

- Define source of truth per object and whether the client can create authoritative writes.
- Use idempotent mutation IDs for retry and replay.
- Track sync state, version, tombstones, and conflict resolution rules.
- Separate local draft state from committed server state.
- Make background sync observable to users and operators.
- Avoid hidden last-write-wins for business-critical data.

## Edge Runtime Checks

- Know platform limits: CPU time, memory, cold start, package size, filesystem, sockets, region, and secrets model.
- Keep edge logic small: auth, routing, cache, light personalization, request shaping.
- Avoid placing complex transactions or hard-to-debug state machines at the edge unless latency requires it.
- Define origin fallback and cache purge strategy.

## Security and Privacy

- Treat the client as untrusted even when it has a signed app binary.
- Never store long-lived privileged secrets on client devices.
- Encrypt sensitive local data where platform support and threat model require it.
- Enforce authorization server-side for every sync and API operation.
- Consider device loss, shared devices, rooted/jailbroken devices, browser extensions, and malicious local storage edits.

## Review Smells

- "Offline support" means only cached reads, not queued writes and conflict handling.
- Edge function owns durable business state without recovery tooling.
- Client-side role checks are the only authorization.
- Push notifications, background jobs, or sync retries have no idempotency.
- Local storage contains secrets, raw PII, or unscoped tokens.
- App update and backward compatibility are not addressed.

## Expected Outputs

- Client/server/edge responsibility split.
- Local data and sync model.
- Conflict resolution and retry policy.
- Platform/runtime constraint register.
- Security and privacy model for device/browser/edge.
- ADR candidates for offline-first, sync protocol, edge placement, client runtime, and local storage.
