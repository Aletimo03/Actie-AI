#!/usr/bin/env bash
# Runs a release on the AWS server, without SSH (Session Manager):
#   deploy/aws/deploy.sh [full-commit-sha]   (default: HEAD, whose images CI must have published)
# A rollback is the same command with an older commit.
set -euo pipefail
cd "$(dirname "$0")"
RELEASE=${1:-$(git rev-parse HEAD)}
INSTANCE=$(terraform output -raw instance_id)
REGION=$(terraform output -raw region)

id=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript --comment "actie release $RELEASE" \
  --parameters "commands=[\"/opt/actie/up.sh $RELEASE\"]" \
  --query Command.CommandId --output text)
echo "release $RELEASE sent ($id), waiting..."
aws ssm wait command-executed --region "$REGION" --command-id "$id" --instance-id "$INSTANCE" || true
aws ssm get-command-invocation --region "$REGION" --command-id "$id" --instance-id "$INSTANCE" \
  --query '[Status, StandardOutputContent, StandardErrorContent]' --output text | tail -20
