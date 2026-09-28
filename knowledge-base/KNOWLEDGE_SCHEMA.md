# Knowledge Entry Schema

Every durable entry should answer five questions:

1. **Context** — where and when did this apply?
2. **Evidence** — what proves it?
3. **Rule** — what should Pravidhi do next time?
4. **Validation** — how do we know the rule works?
5. **Lifecycle** — when should the knowledge be reviewed or retired?

## Promotion rules

T0 observation → T1 reproduced → T2 controlled deployment →
T3 production evidence → T4 independent review.

Promotion must not skip evidence.

## Conflict handling

When two entries conflict:
- prefer newer evidence only when the environment/version matches;
- preserve the older entry as historical context;
- mark the conflict explicitly;
- update the owning SOP or test;
- do not silently overwrite security controls.

## Retrieval tags

Use stable tags such as:
`mcp`, `oauth`, `rbac`, `tenant`, `approval`, `terminal`,
`filesystem`, `audit`, `recording`, `deployment`, `windows`,
`linux`, `termux`, `testing`, `incident`.

## Anti-pattern

Do not store secrets, tokens, passwords, private keys, customer data,
or instructions whose purpose is to bypass Pravidhi OS security controls.
