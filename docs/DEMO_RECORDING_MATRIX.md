# Pravidhi OS — Action & Demo Recording Matrix

## Purpose

This is the canonical checklist for recording and documenting Pravidhi OS capabilities. Each demo recording must identify the action, authorization boundary, expected result, and evidence captured.

**Important:** an action appearing in the architecture is not proof that it is currently exposed by the deployed public MCP. Status is therefore recorded explicitly.

## Action categories

| ID | Action category | Demo evidence | Current status |
|---|---|---|---|
| ACT-01 | Health | Service health and availability | LIVE — public MCP |
| ACT-02 | Capabilities | Published MCP capability inventory | LIVE — public MCP |
| ACT-03 | Authentication | User/service authentication and token validation | ARCHITECTURE / deployment-dependent |
| ACT-04 | Authorization / RBAC | Role and permission enforcement | ARCHITECTURE / deployment-dependent |
| ACT-05 | Tenant isolation | Tenant-scoped resource boundaries | ARCHITECTURE / deployment-dependent |
| ACT-06 | Approval gates | Explicit approval before high-risk operations | ARCHITECTURE / deployment-dependent |
| ACT-07 | Execution | Authorized task/job execution | ARCHITECTURE / deployment-dependent |
| ACT-08 | Filesystem | Controlled file inspection/change inside authorized workspace | ARCHITECTURE / deployment-dependent |
| ACT-09 | Terminal / shell | Constrained command execution | ARCHITECTURE / deployment-dependent |
| ACT-10 | Screen agent | Authorized screen interaction/capture workflow | ARCHITECTURE / deployment-dependent |
| ACT-11 | Browser / external systems | Controlled browser or external-system operation | ARCHITECTURE / deployment-dependent |
| ACT-12 | Audit | Correlated audit evidence for actions and approvals | ARCHITECTURE / deployment-dependent |
| ACT-13 | MCP integration | MCP transport, discovery, tool invocation and boundaries | LIVE — transport; tool surface is limited |
| ACT-14 | Fail-closed behavior | Unauthorized/high-risk requests are rejected safely | RELEASE GATE / test per deployment |

## Required recording evidence

1. Action ID.
2. Human-readable action name.
3. Starting state.
4. User/request that triggered it.
5. Authentication context, without exposing secrets.
6. Authorization/tenant context, without exposing sensitive identifiers.
7. Approval step, when applicable.
8. UI or terminal evidence of the operation.
9. Result and error state.
10. Timestamp.
11. Recording filename.
12. Related documentation/test case.
13. Whether the action is live, deployment-dependent, planned, or blocked.

## Recording policy

The Demo Recorder is browser-local. Screen, camera and microphone capture remain in the browser and are not uploaded to the Pravidhi control plane.

Do not record API keys, OAuth client secrets, bearer tokens, passwords, private keys, credential files, customer data, or unrelated personal information.

## Release recording sequence

Use the same sequence for every release:

1. Health check.
2. Capability discovery.
3. Authentication.
4. Authorization/RBAC.
5. Tenant isolation.
6. Approval gate.
7. Execution.
8. Filesystem.
9. Terminal.
10. Screen agent.
11. Browser/external system.
12. Audit trail.
13. MCP invocation.
14. Negative/fail-closed tests.

If a capability is not actually deployed, record the documentation/status page instead of simulating a successful operation.

## Current public MCP boundary

The public MCP endpoint currently exposes these read-only tools:

- pravidhi_health
- pravidhi_capabilities

Privileged control is documented as requiring authenticated, tenant-scoped authorization. It must not be represented in a public demo as available until the corresponding authenticated MCP tools and authorization server are deployed and tested.

## Evidence naming

Recommended:

pravidhi-os-v<version>-<action-id>-<short-name>-<YYYYMMDD>.webm

Matching event log:

pravidhi-os-v<version>-<action-id>-<short-name>-<YYYYMMDD>.json

## Acceptance criteria

A release is recorded and documented only when every applicable action has a documented implementation/status, repeatable demo procedure, positive test, negative/safety test where relevant, recording evidence or an explicit reason recording is unavailable, no secrets in evidence, and a traceable release/version reference.