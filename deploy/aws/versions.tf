terraform {
  required_version = ">= 1.16.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.69.1" # 2026-10-15: pinned like every other dependency (>= 14 days old)
    }
  }
  # State stays local and gitignored: it holds resource IDs, no secrets (the model key is
  # in SSM, the other secrets are generated on the server).
}

provider "aws" {
  region = var.region

  default_tags {
    tags = { project = "actie-ai", managed-by = "terraform" }
  }
}
