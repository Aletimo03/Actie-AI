# Actie AI on AWS: one EC2 instance with Compose

Terraform creates one `t3.small` in `eu-north-1` running the stack in `server/compose.yaml`
(Postgres, the API, nginx) behind Caddy, which gets a Let's Encrypt certificate for
`<ip-with-dashes>.sslip.io` (or your `domain`). No SSH (Session Manager), no load balancer,
no NAT gateway: about $15 a month from the Free plan's credits. Lecture 13 has the why.

A release is one commit: the server runs the images CI published as `sha-<commit>` and
fetches that commit's `server/` files, so config and code always match.

## First time

1. CI has published the images for the commit (the `publish` job is green), and both GHCR
   packages are public (GitHub → Packages → actie-api / actie-web → Change visibility).
2. The model key into SSM, encrypted (reads it from `.env`, prints nothing):
   `deploy/aws/put-secret.sh`
3. Create everything (from `deploy/aws/`), with a commit whose images exist:
   `terraform init`
   `terraform apply -var "release=$(git rev-parse HEAD)" [-var alert_email=you@example.com]`
4. A few minutes later: `terraform output url`. First-boot log on the server:
   `$(terraform output -raw shell)`, then `sudo tail -f /var/log/actie-bootstrap.log`

## Releases and rollbacks

`deploy/aws/deploy.sh [commit]` (default HEAD) runs `server/up.sh <commit>` through Session
Manager: pull the images, load the law if missing, restart. A rollback is the same command
with an older commit.

## Removing it

`terraform destroy` deletes the server, its disk (the database) and the IP. The daily
snapshots are kept until deleted from the EC2 console.
