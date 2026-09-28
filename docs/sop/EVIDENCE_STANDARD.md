# Pravidhi OS — Evidence & Recording Standard

## Evidence classes
- E1: public health/capability evidence
- E2: authentication evidence
- E3: authorization/RBAC evidence
- E4: tenant-isolation evidence
- E5: approval evidence
- E6: execution evidence
- E7: filesystem/terminal evidence
- E8: audit evidence
- E9: negative/fail-closed evidence

## Evidence quality
Evidence must be:
1. attributable to a release;
2. reproducible by another operator;
3. minimal in sensitive information;
4. linked to a test or requirement;
5. clear about LIVE, deployment-dependent, planned, or blocked status.

## Recorder controls
Use browser-local capture. Confirm microphone, camera, screen, tab,
and system-audio permissions before recording. Stop capture immediately
if secrets or private information appear.

## Manifest minimum
```json
{
  "action_id": "ACT-XX",
  "version": "x.y.z",
  "commit": "<sha>",
  "timestamp": "<ISO-8601>",
  "environment": "<environment>",
  "status": "LIVE|DEPLOYMENT_DEPENDENT|PLANNED|BLOCKED",
  "recording": "<filename>",
  "tests": ["<test-id>"],
  "notes": "<operator notes>"
}
```
## Evidence review questions

- Does the recording prove the stated capability?
- Is the authorization boundary visible enough to audit?
- Is any secret or personal data visible?
- Can the test be repeated from the documented starting state?
- Does the evidence match the deployed version?
- Is the failure path demonstrated where risk warrants it?
- Is the corresponding lesson recorded?

## Evidence retention
Keep source recordings locally unless there is an approved reason to
publish or transfer them. Treat manifests as the durable index.

## Truthfulness rule
Architecture, source code, and planned capability are not equivalent to
a deployed production capability. The evidence status must reflect reality.
