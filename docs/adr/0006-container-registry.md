# 0006. Container registry: build only in v0.1, Amazon ECR with OIDC in v0.2

- Status: Accepted
- Date: 2026-09-26

## Context

CI builds and scans the images from v0.1 onwards. The images will be deployed on AWS later. The project rules forbid long-lived credentials in the repository or in CI secrets, and require OIDC for access to AWS.

## Decision

- **v0.1: build and scan only.** CI builds the `api` and `worker` images and scans them with Trivy, but does not push them anywhere.
- **v0.2: push to Amazon ECR.** GitHub Actions authenticates through **OIDC** by assuming an IAM role that trusts only this repository and its protected branches, and that grants only push rights on the pulseWatch repositories. The ECR repositories and the IAM role are managed with Terraform.
- Images will be tagged with the commit SHA (immutable tags), never deployed from `latest`.

## Alternatives considered

- **GitHub Container Registry (GHCR)**: simple to use with `GITHUB_TOKEN`, but a registry outside AWS, so the cluster would need extra registry credentials. ECR integrates with IAM, image scanning and the future EKS cluster.
- **Push to ECR from v0.1**: requires the AWS account, Terraform and IAM work first, which is outside the v0.1 scope.
- **Static AWS access keys in CI secrets**: forbidden by the project security rules and a common source of leaks.

## Consequences

- v0.1 needs no cloud credentials at all.
- v0.2 requires Terraform for ECR and the OIDC role before the push step, with explicit approval before `terraform apply`.
- Deployments reference images by SHA, which suits GitOps promotion.
