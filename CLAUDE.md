# pulseWatch — Engineering guidelines

Uptime monitoring platform built with production practices: containers, infrastructure as code, GitOps and observability.

## Workflow
- Explain the intent and trade-offs before any change; keep changes small and focused.
- Infrastructure, Kubernetes and CI changes: propose the design first, implement only after approval.
- Record every architecture decision as an ADR in `docs/adr/`.
- One issue per task, one pull request per change, conventional commit messages.

## Quality gates
- After each change, run the relevant checks: tests, `terraform fmt` and `validate`, `helm lint`, `trivy`.
- Never mark a task done while a check fails.

## Security
- Ask for explicit approval before `terraform apply`, `terraform destroy` or any command that changes AWS resources.
- No secrets, keys or credentials in the repository; use AWS Secrets Manager and OIDC.

## References
- Tool versions: `docs/versions.md`
- Architecture decisions: `docs/adr/`
