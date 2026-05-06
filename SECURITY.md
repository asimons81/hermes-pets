# Security Policy

Please do not report security issues as public GitHub issues.

Send security reports to Tony Simons at tony@tonysimons.dev. Include enough detail to reproduce the issue, the affected commands or files, and any local environment assumptions that matter.

## Security-Sensitive Areas

- Local command execution
- WebSocket bridge behavior
- Local state and file paths
- Custom pet import and validation
- Packaged overlay assets
- Anything that could expose secrets or private local files

## Out of Scope

- Cosmetic animation bugs
- Ordinary CLI errors without security impact
- Issues requiring malicious local machine access with no meaningful privilege boundary crossed

When in doubt, report privately first.
