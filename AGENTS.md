# Repository rules

- Every change starts with a feature or bug issue.
- Use standard Gitflow: feature/* and fix/* branch from develop and target develop; release/* targets main and merges back into develop; hotfix/* branches from main and merges into both.
- Use TDD: add a failing behavior test, implement the smallest complete change, refactor, run checks. Preserve tests-first commits where practical.
- Never commit secrets, real installation IP addresses, hostnames, serial numbers, MACs, account details, personal information or raw installation captures. Fixtures must be synthetic.
- Device configuration belongs only in Home Assistant local configuration storage. Keep connection errors generic. Do not log transport keys or device identifiers.
- Keep all inverter communication read-only. No control registers or write services.
- Keep hardware compatibility claims explicit about tested versus unverified support.
- Run pytest, ruff check and ruff format --check before a PR. No direct feature changes on main.
