# Pravidhi OS Knowledge Base

## Mission
Convert operational experience into durable, searchable knowledge that
improves Pravidhi OS without weakening its security boundary.

## Knowledge flow
```
record → extract → validate → classify → store → review → improve → retest
```

## Sources
- Recording manifests and action evidence
- SOPs and security model
- Test results
- Incident/failure analysis
- Deployment notes
- Architecture decisions
- Research/training-loop lessons
- Verified operator observations

## Categories
- `architecture/` — system design and boundaries
- `security/` — threats, controls, negative tests
- `operations/` — deployment and runbooks
- `recordings/` — evidence indexes
- `lessons/` — validated lessons
- `decisions/` — architecture/product decisions
- `skills/` — reusable procedural knowledge

## Trust levels
T0 = unverified observation
T1 = reproduced locally
T2 = tested in controlled deployment
T3 = production evidence
T4 = independently reviewed

Never promote a lesson without evidence.
## Self-improvement loop

For each completed workflow:
1. Capture the outcome.
2. Compare expected vs actual behavior.
3. Record failure modes and successful patterns.
4. Identify the smallest useful lesson.
5. Add or update a test.
6. Update the relevant SOP/skill.
7. Re-run validation.
8. Promote the lesson only when evidence supports it.

## Safety constraints

The knowledge base must never become an authorization bypass.
Learned patterns cannot override identity, tenant isolation, RBAC,
approval gates, path controls, command allowlists, or audit requirements.

Generated skills remain drafts until validated.

## Review cadence

At each release:
- review new lessons;
- deduplicate patterns;
- retire obsolete guidance;
- verify references to current code/tests;
- run the recording matrix;
- update the release knowledge index.
