# Pravidhi OS — Feature & Use-Case Guide

## Purpose
This guide explains what each Pravidhi OS feature is for, when to use it,
what a typical request looks like, and what security boundary applies.

Examples are representative workflows, not claims that every capability is
enabled in every deployment.

## 1. Secure machine connection
Provides a controlled bridge between an AI client and a machine the user has
explicitly authorized.

Use cases:
- Developer asks an agent to inspect a local project.
- IT operator asks for service diagnostics on a managed server.
- DevOps engineer asks an agent to inspect a deployment workspace.
- Security engineer asks for authorized log/configuration inspection.

Example: “Inspect the application logs and identify why the service is
restarting.”

Boundary: connection does not equal unrestricted administrator access. The
control plane still evaluates identity, tenant, role, capability, policy,
and approval requirements.

## 2. Authentication / OIDC / OAuth
Establishes the identity under which protected operations are requested.

Use cases:
- Developer connects ChatGPT to an authorized workstation.
- Employee signs in through the organization's identity provider.
- Service integration obtains a scoped access token.
- Administrator revokes access at the identity layer.

Example: “Connect using my organization account and show my authorized
Pravidhi workspace.”

Security: tokens are validated for issuer, signature, audience,
expiry/not-before and required scopes. An MCP URL alone is not authorization.

## 3. RBAC
Separates read-only users, operators, and administrators.

Typical model:
- viewer/user → information and read-only capabilities
- operator → approved operational actions
- admin → administrative actions

Use cases:
- Helpdesk staff inspect status without changing systems.
- DevOps operators execute approved maintenance.
- Security administrators resolve sensitive approvals.
- Contractors receive only minimum required permissions.

Example: “Show service health” may be available to a read-only user, while
“restart this service” can require operator authorization and approval.

RBAC answers who may request an action; approval answers whether the sensitive
action may proceed now.

## 4. Tenant / workspace isolation
Keeps resources, approvals, executions, audit records and filesystem
workspaces associated with the authenticated tenant.

Use cases:
- MSP manages several customer environments.
- Company separates production and development workspaces.
- Multiple teams share one Pravidhi installation.
- Consultant works across explicitly authorized customer tenants.

Example: “Read the deployment file in Customer A's workspace.”

Security: knowing another tenant's resource ID must not grant access.

## 5. Capability authorization
Separates individual capabilities instead of treating the agent as one
all-powerful identity.

Examples:
- pravidhi.read — inspect information.
- pravidhi.execute — authorized execution.
- pravidhi.admin — administrative operations.

Use cases:
- Observability agent gets read-only access.
- Deployment agent gets execution access.
- Platform administrator gets administrative access.

Example: “Allow this agent to read logs but not modify files.”

A scope is one part of authorization; deployment policy and RBAC still apply.

## 6. Human approval gates
Adds an explicit checkpoint before consequential operations.

Use cases:
- Production configuration change.
- File deletion or overwrite.
- Maintenance command.
- Release deployment.
- Firewall or security configuration change.

Example: “Prepare the production restart, but wait for operator approval
before executing it.”

Flow: request → authenticate → authorize → approval → revalidate →
execute → audit.

Approvals should bind tenant, requester, intended operation, target/resource,
expiry and approval state.

## 7. Terminal / command execution
Provides constrained command execution rather than an unrestricted remote shell.

Use cases:
- Check service status.
- Run approved test suites.
- Inspect processes/resources.
- Execute an approved deployment command.
- Run a diagnostic script in an authorized workspace.

Example: “Run the approved test suite and return the failing tests.”

Safety: command allowlists, constrained arguments, tenant workspace
boundaries, unprivileged execution, approval, status/cancellation and audit.

## 8. Filesystem read
Reads files within the authorized tenant/workspace boundary.

Use cases:
- Inspect application configuration.
- Review deployment manifests.
- Read source code for debugging.
- Analyze logs or generated reports.
- Compare configuration files.

Example: “Read the deployment manifest and identify the configured port.”

Path traversal, absolute-path escapes, symlink tricks and alternate encodings
must be rejected.

## 9. Filesystem write
Changes files inside an authorized workspace when writes are permitted.

Use cases:
- Update configuration.
- Apply an approved code fix.
- Generate a report.
- Update a deployment manifest.
- Create documentation from an approved workflow.

Example: “Apply the approved configuration change and show the diff.”

Consequential writes should require approval and use path normalization,
tenant confinement, atomic semantics where appropriate, and audit logging.

## 10. Process and execution lifecycle
Tracks an operation after submission.

Use cases:
- Monitor a long-running build.
- Check deployment progress.
- Retrieve an authorized task result.
- Determine whether an execution completed or failed.
- Support cancellation where implemented.

Example: “Check the deployment execution and tell me whether it completed.”

Every execution should remain associated with its tenant and request/correlation
identifier.

## 11. Audit events
Creates structured evidence of security-relevant operations.

Use cases:
- Investigate who requested a production change.
- Review approval and execution history.
- Correlate an incident with a command.
- Produce operational evidence for an audit.
- Diagnose why an automated task was rejected.

Example: “Show audit events for the last approved filesystem change.”

Audit records must be tenant-filtered and must not expose credentials.

## 12. Request IDs and correlation
Connects related requests across control plane, agent, execution and audit
layers.

Use cases:
- Trace a failed deployment.
- Correlate approval with execution.
- Investigate a security event.
- Debug a distributed workflow.

Example: “Trace request ID X from approval through execution and audit.”

Clients should preserve X-Request-ID when present.

## 13. Rate limiting
Limits request volume to reduce abuse and protect the control plane.

Use cases:
- Protect a public MCP endpoint.
- Prevent accidental request loops.
- Limit aggressive automation.
- Reduce credential-abuse blast radius.

Example: a diagnostic loop repeatedly requests health data; rate limiting
prevents it from overwhelming the control plane.

Rate limiting is a protection layer, not an authorization mechanism.

## 14. Fail-closed behavior
Rejects an operation when a required security decision cannot be safely
evaluated.

Examples:
- Missing identity → reject.
- Invalid token → reject.
- Missing tenant → reject tenant-scoped operation.
- Insufficient role/scope → reject.
- Missing approval → reject consequential operation.
- Invalid path → reject.
- Disallowed command → reject.

Use case: authorization context disappears during maintenance. Pravidhi stops
rather than silently downgrading to an unrestricted mode.

## 15. MCP integration
Exposes Pravidhi capabilities to compatible AI clients through the Model
Context Protocol.

Use cases:
- ChatGPT inspects an authorized development environment.
- Codex performs approved development operations.
- Internal MCP agents consume Pravidhi capabilities.
- Teams standardize AI-to-machine access behind one policy boundary.

Example: “Inspect the failing test, propose the fix, and wait for approval
before modifying files.”

MCP discovery/health can be public while protected operations remain
authenticated.

## 16. Screen / desktop agent
Enables optional interaction with an attached desktop agent.

Use cases:
- Inspect a GUI-only application.
- Demonstrate an application workflow.
- Diagnose desktop configuration.
- Capture visual evidence of an authorized workflow.

Example: “Open the approved application and verify the configuration.”

A screen API existing does not prove a screen agent is attached. The agent
must be registered, authenticated and appropriately scoped.

## 17. Browser / external-system workflows
Provides a controlled pattern for approved external systems when such
integrations are deployed.

Use cases:
- Open an internal dashboard.
- Inspect a deployment portal.
- Perform an approved administrative workflow.
- Collect evidence from a web management console.

Example: “Open the authorized monitoring console and capture service status.”

External actions require explicit authorization and should not be represented
as available merely because a browser integration exists in architecture.

## 18. CLI / AgentOS runtime
Supports self-hosted and developer-oriented operation.

Use cases:
- Initialize a local agent environment.
- Configure a self-hosted deployment.
- Run development/testing workflows.
- Integrate Pravidhi into an engineering toolchain.

Example: “Initialize AgentOS and configure the approved control-plane URL.”

Secrets should come from environment variables or a secret manager.

## 19. Deployment modes

### Headless server agent
Infrastructure/backend operations.
Example: check a Linux service, inspect logs, run approved maintenance.

### Desktop agent
Workstation and GUI workflows.
Example: inspect an authorized local project and interact with a desktop app.

### Hybrid deployment
Centralized control plane with registered execution endpoints.
Example: IT manages multiple authorized endpoints with centralized identity,
RBAC, approvals and audit.

## 20. Recording and evidence
The Demo Recorder turns workflows into reproducible evidence.

Use cases:
- Record an MCP capability demonstration.
- Capture a security-control test.
- Document installation.
- Produce release evidence.
- Train operators.

Example: record authentication → approval → execution → audit.

Never record passwords, tokens, private keys, customer data or unrelated
personal information.

## 21. Knowledge base
The knowledge base converts verified experience into reusable knowledge.

Use cases:
- Store lessons from failed deployments.
- Record troubleshooting patterns.
- Link evidence to SOP changes.
- Preserve architecture decisions.
- Build reusable operator skills.

Example: a Windows deployment failure is recorded with evidence, root cause,
fix, regression test and related SOP.

Knowledge should progress through evidence levels rather than becoming trusted
because an agent generated it.

## 22. Self-improvement / training loop
Workflow: record → analyze → detect patterns → generate lesson/skill
candidate → validate → test → promote knowledge.

Use cases:
- Detect recurring errors.
- Identify successful execution patterns.
- Generate draft remediation skills.
- Measure success rate and latency.
- Detect regressions.

Example: three similar failures reveal a root cause; Pravidhi creates a draft
remediation skill, which is tested before becoming trusted knowledge.

Generated knowledge must never override security controls.

## 23. Security operations use cases

### SOC investigation
“Read authorized incident logs, identify relevant events, and prepare a
timeline.”
Controls: read scope, tenant boundary, audit.

### Vulnerability remediation
“Apply the approved configuration fix to the test workspace and run
validation.”
Controls: execute scope, approval, filesystem confinement, audit.

### Incident response
“Collect approved diagnostic files and process information without modifying
the system.”
Controls: read-only capability and evidence trail.

## 24. DevOps use cases

### Deployment
“Check the build, deploy the approved artifact, and report the execution ID.”

### CI troubleshooting
“Inspect failing test output and identify the first actionable error.”

### Infrastructure maintenance
“Prepare the maintenance command and wait for approval.”

The same workflow can span local development, staging and production when
each environment has its own authorization boundary.

## 25. Developer use cases

### Codebase analysis
“Inspect the repository and explain where authentication is handled.”

### Controlled code change
“Update the failing function, show the diff, run tests, and wait for approval
before writing to the protected workspace.”

### Local automation
“Generate documentation from the current source and save it in the approved
docs directory.”

## 26. IT / helpdesk use cases

### Diagnostics
“Check disk space, running services and recent errors.”

### Configuration inspection
“Read the authorized network configuration and identify mismatches.”

### Controlled remediation
“Prepare the documented remediation and execute it only after approval.”

A helpdesk role can remain read-only while operators receive execution rights.

## 27. Business / operations use cases
Pravidhi can standardize routine computer tasks behind the same authorization
and audit boundary.

Examples:
- Generate operational reports.
- Prepare files for an approved process.
- Run scheduled maintenance.
- Validate a service before a business process begins.

## 28. What Pravidhi OS is not
Pravidhi OS is not intended to be:
- an unrestricted remote shell;
- a mechanism for bypassing authentication;
- a way to evade tenant boundaries;
- an automatic administrator for every machine;
- a substitute for human approval of consequential changes;
- proof that an architectural feature is currently deployed.

The deployed tool surface and environment status determine what can actually
be performed.

## 29. Recommended workflow selection

| Goal | Typical capability path |
|---|---|
| Inspect system | identity → tenant → read → audit |
| Diagnose issue | identity → tenant → read → analysis → audit |
| Modify file | identity → tenant → RBAC → approval → filesystem write → audit |
| Run command | identity → tenant → RBAC → policy → approval → execution → audit |
| Investigate incident | identity → tenant → read → audit/evidence |
| Deploy change | identity → tenant → RBAC → approval → execution → status → audit |
| GUI workflow | identity → registered screen agent → capability → approval |
| Learn from failure | record → analyze → lesson → regression test → knowledge |

## 30. Rule for all examples
Every use case should identify:
1. user/request;
2. authorized machine or tenant;
3. required capability;
4. whether approval is required;
5. expected result;
6. evidence/audit trail;
7. failure behavior.

This keeps examples useful without implying that an example operation is
automatically permitted in every deployment.
