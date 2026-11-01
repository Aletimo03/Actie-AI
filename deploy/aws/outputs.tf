output "url" {
  description = "The app, once the server has started (a few minutes after apply)."
  value       = "https://${local.site_address}"
}

output "public_ip" {
  description = "For your domain's A record, if you add one later."
  value       = aws_eip.server.public_ip
}

output "instance_id" {
  value = aws_instance.server.id
}

output "shell" {
  description = "A shell on the server, without SSH."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.server.id}"
}

output "region" {
  value = var.region
}
