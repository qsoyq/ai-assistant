# Security Policy

## Supported Versions

Security fixes target the current `main` branch and the latest released package version.

## Reporting a Vulnerability

Do not open a public issue for suspected credential leaks or exploitable vulnerabilities.

Report security issues privately to the repository owner through GitHub. Include:

- Affected command or module.
- Reproduction steps.
- Expected impact.
- Any safe proof-of-concept details.

The maintainer will acknowledge the report, assess impact, and coordinate a fix before public disclosure when needed.

## Secret Handling

Never commit real `.env` files, API tokens, passwords, certificates, private keys, or service-account files. If a secret may have been committed, revoke it before removing it from the repository history.
