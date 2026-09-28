# Pravidhi OS — Recording Workflow SOP

## 1. Purpose
Define a repeatable, secure process for recording product demonstrations,
release evidence, security tests, and operational workflows.

## 2. Scope
Applies to the Demo Recorder, MCP demonstrations, control-plane actions,
terminal/filesystem workflows, authentication/RBAC tests, and release evidence.

## 3. Core rule
Record only capabilities that are actually deployed and tested. Never simulate
a successful privileged operation when the capability is unavailable.

## 4. Security boundary
Use the chain:
identity → tenant → role → capability → policy → approval → execution → audit.

Recording must show the boundary without exposing credentials or sensitive data.

## 5. Preparation checklist
- Confirm release/version and commit.
- Confirm target device and environment.
- Confirm test tenant/workspace.
- Confirm authentication state.
- Confirm test data contains no secrets or customer data.
- Open the Demo Recorder.
- Select the Action ID from the recording matrix.
- Prepare positive and negative test cases.
- Verify expected evidence filename.

## 6. Recording procedure
1. State the Action ID and objective.
2. Show starting state.
3. Trigger the user request.
4. Show relevant authorization context without secrets.
5. Show approval when required.
6. Execute the operation.
7. Capture result and error state.
8. Verify audit/correlation evidence.
9. Stop recording.
10. Export the evidence manifest.
## 7. Evidence requirements

Each recording should have:
- Action ID and human-readable name.
- Version/commit reference.
- Timestamp.
- Environment/device.
- Starting state.
- Request/intent.
- Auth/RBAC boundary.
- Approval evidence where applicable.
- Result/error.
- Related test case.
- Recording filename.
- Evidence manifest.

## 8. Naming convention
Recording:
pravidhi-os-v<version>-<action-id>-<short-name>-<YYYYMMDD>.webm

Manifest:
pravidhi-os-v<version>-<action-id>-<short-name>-<YYYYMMDD>.json

## 9. Prohibited capture
Never record API keys, OAuth secrets, bearer tokens, passwords,
private keys, credential files, customer data, or unrelated personal data.

## 10. Negative testing
For every protected capability, test at least:
- missing identity
- invalid/expired token
- insufficient scope
- insufficient role
- wrong tenant
- missing approval
- expired approval
- invalid target/path
- disallowed command

Expected behavior is fail-closed.

## 11. Review gate
A recording is accepted only when:
- implementation status is truthful;
- evidence is reproducible;
- secrets are absent;
- positive and applicable negative tests exist;
- documentation links to the implementation/test;
- release/version is traceable.

## 12. Learning capture
After every recording, create a lesson entry containing:
Observation → Evidence → Root cause → Lesson → Action → Validation.

The lesson becomes part of the Pravidhi OS knowledge base and may inform
future SOP revisions, tests, skills, or training-loop analysis.
