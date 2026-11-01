variable "region" {
  description = "Where the server runs: in the EU, so descriptions and answers stay there at rest."
  type        = string
  default     = "eu-north-1" # Stockholm: the account's project region
}

variable "release" {
  description = "Full commit SHA to run: its images (sha-<commit>, published by CI) and its deploy/aws/server files."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.release))
    error_message = "Use a full 40-character commit SHA (git rev-parse HEAD) whose images CI has published."
  }
}

variable "instance_type" {
  description = "2 GB is enough for Postgres, the API, nginx and Caddy (about 450 MB in use)."
  type        = string
  default     = "t3.small" # x86: our images are built for linux/amd64
}

variable "domain" {
  description = "Your own domain, if any. Empty: <ip-with-dashes>.sslip.io, free, with a real certificate."
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Where the monthly budget alert goes. Empty: no budget is created."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Alert when forecast or actual spend passes this (the Free plan can't bill, but credits run out)."
  type        = number
  default     = 20
}
