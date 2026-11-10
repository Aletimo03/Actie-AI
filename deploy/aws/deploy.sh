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

# Our own loop: the AWS CLI's waiter gives up after 100 s, and a release that pulls new
# images can take longer. The invocation may not exist yet right after the send.
status=Pending
while [[ $status =~ ^(Pending|InProgress|Delayed)$ ]]; do
  sleep 5
  status=$(aws ssm get-command-invocation --region "$REGION" --command-id "$id" \
    --instance-id "$INSTANCE" --query Status --output text 2>/dev/null || echo Pending)
done

aws ssm get-command-invocation --region "$REGION" --command-id "$id" --instance-id "$INSTANCE" \
  --query '[StandardOutputContent, StandardErrorContent]' --output text | tail -20
echo "release $RELEASE: $status"
[ "$status" = Success ]  # a failed release fails this script
