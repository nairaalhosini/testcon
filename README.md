# Bad Single File Python Repo

This repository is intentionally bad and unsafe. It is designed for code quality, security, duplication, reliability, and coverage tooling demos.

## Files

- `mega_bad_app.py` — one large Python application file with many intentional issues.
- `coverage.xml` — fake Cobertura-style coverage output showing low coverage.

## Intentional issues

- SQL injection
- Command injection
- Path traversal
- Unsafe `eval`, `pickle`, and YAML loading
- Hardcoded secrets
- Plaintext passwords
- Sensitive logging
- Duplicate functions and duplicate logic
- Global mutable state
- Race-prone background worker
- Random/flaky behavior
- Silent exception swallowing
- Missing validation
- Broken authorization
- Misleading health checks

Do not run this as a real service.
