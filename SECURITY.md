# Security Policy

## Supported Versions

Security fixes are applied to the latest chart release and the current backend/web
image lines. Only the most recent minor line of the chart is guaranteed to
receive security fixes.

| Version | Supported |
| --- | --- |
| Latest chart release | Yes |
| Older releases | Best effort — upgrade first |

## Reporting a Vulnerability

Please report security issues privately to **support@artifactkeeper.com** with
"[security]" in the subject line. Do not open a public issue for an
unpatched vulnerability.

Include:

- A description of the issue and its impact
- Steps to reproduce or a proof of concept
- The chart version and deployment topology (Helm, ArgoCD, docker-compose, AMI)
- Whether you believe the issue is exploitable in a default install

We will acknowledge your report within 3 business days and aim to provide an
assessment within 10. If the issue is confirmed we will prepare a fix, credit
you in the release notes (unless you prefer otherwise), and coordinate
disclosure timing with you.

## Scope Notes

- This repository contains the Helm chart, Terraform modules, and example
  deployment scripts. Vulnerabilities in the application itself
  (backend/web/scanner images) are also welcome here and will be routed
  internally.
- Demo and example values files intentionally contain non-production
  credentials; those are not vulnerabilities. A credential that works against
  anything real is — please report it immediately.
- CI runs on a mix of GitHub-hosted and self-hosted runners; if you find a
  CI/CD weakness, report it privately rather than demonstrating it with a
  pull request.
