# One EC2 instance running our Compose stack behind Caddy (automatic HTTPS). No SSH: Session
# Manager instead. No load balancer and no NAT gateway: about $15 a month, not $45-65.

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_vpc" "default" {
  default = true
}

locals {
  site_address = var.domain != "" ? var.domain : "${replace(aws_eip.server.public_ip, ".", "-")}.sslip.io"
  secret_path  = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/actie/*"
}

# Firewall: the web only. No port 22: the server is reached through Session Manager.
resource "aws_security_group" "server" {
  name        = "actie-server"
  description = "HTTP and HTTPS in for Caddy, everything out for images, the LLM provider and Lets Encrypt"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP for the Lets Encrypt challenge and the redirect to HTTPS"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# The server's own identity: Session Manager, and reading the model key from SSM. Nothing else.
resource "aws_iam_role" "server" {
  name = "actie-server"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "session_manager" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "read_secrets" {
  name = "read-actie-parameters"
  role = aws_iam_role.server.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = local.secret_path },
      {
        Effect    = "Allow"
        Action    = ["kms:Decrypt"]
        Resource  = "*"
        Condition = { StringEquals = { "kms:ViaService" = "ssm.${var.region}.amazonaws.com" } }
      },
    ]
  })
}

resource "aws_iam_instance_profile" "server" {
  name = "actie-server"
  role = aws_iam_role.server.name
}

resource "aws_instance" "server" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.server.name
  vpc_security_group_ids = [aws_security_group.server.id]

  user_data = templatefile("${path.module}/server/bootstrap.sh", {
    region       = var.region
    release      = var.release
    site_address = local.site_address
  })

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # containers can't reach it: no stealing the role
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
    tags        = { snapshot = "daily" }
  }

  # A newer AMI or a changed bootstrap must not replace the server (and its database):
  # releases go through deploy.sh. Rebuild deliberately with -replace if ever needed.
  lifecycle {
    ignore_changes = [ami, user_data]
  }

  tags = { Name = "actie-server" }
}

# A fixed public IP: the sslip.io name (or your domain's A record) depends on it.
resource "aws_eip" "server" {
  domain = "vpc"
  tags   = { Name = "actie-server" }
}

resource "aws_eip_association" "server" {
  instance_id   = aws_instance.server.id
  allocation_id = aws_eip.server.id
}

# Daily snapshots of the disk (the database lives on it), seven kept.
resource "aws_iam_role" "snapshots" {
  name = "actie-snapshots"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "snapshots" {
  role       = aws_iam_role.snapshots.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "daily" {
  description        = "actie-ai daily disk snapshots 7 kept"
  execution_role_arn = aws_iam_role.snapshots.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]
    target_tags    = { snapshot = "daily" }

    schedule {
      name = "daily"
      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["02:30"]
      }
      retain_rule {
        count = 7
      }
      copy_tags = true
    }
  }
}

resource "aws_budgets_budget" "monthly" {
  count        = var.alert_email != "" ? 1 : 0
  name         = "actie-ai-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}
