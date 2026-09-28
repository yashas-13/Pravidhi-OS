# Pravidhi OS Commercial Roadmap

## Phase 0 — Security hardening

- [x] Explicit public/privileged API boundary
- [x] Fail-closed privileged gateway when auth is missing
- [x] Configurable Bearer service authentication
- [x] Request ID propagation
- [x] Commercial product specification
- [ ] Full OIDC/JWT middleware
- [ ] WebSocket authentication
- [ ] Policy enforcement on every execution path
- [ ] Immutable audit sink
- [ ] Negative authorization test suite

## Phase 1 — Developer release

- [x] npm CLI
- [x] health/provider/login commands
- [ ] init
- [ ] machine registration
- [ ] status
- [ ] capabilities
- [ ] policy
- [ ] audit
- [ ] signed agent identity

## Phase 2 — Pro

- [ ] multi-machine organizations
- [ ] approval inbox
- [ ] usage metering
- [ ] advanced policy packs
- [ ] MCP gateway
- [ ] browser capability
- [ ] desktop capability

## Phase 3 — Team

- [ ] SSO/OIDC
- [ ] SCIM
- [ ] agent registry
- [ ] organization RBAC
- [ ] SIEM export
- [ ] webhook approvals

## Phase 4 — Enterprise

- [ ] private deployment
- [ ] on-prem package
- [ ] data residency options
- [ ] signed/attested agents
- [ ] compliance evidence export
- [ ] SLA/support
- [ ] managed agent security services

## Commercial rule

New execution capabilities must enter through identity → capability → policy → approval → audit. Experimental code must not create a second authorization path.
