# Severity

Every finding uses exactly one level:

| Level | Meaning |
|-------|---------|
| **Blocking** | Must fix before merge or release; breaks correctness, security, or operability. |
| **Advisory** | Should fix; meaningful risk or maintainability cost if deferred. |
| **Observation** | Minor, informational, or low blast-radius; fix when convenient. |

Priority ranking (step 5) sorts by this order first, then cross-reference status, then blast radius.
