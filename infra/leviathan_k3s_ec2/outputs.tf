output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.leviathan_k3s.id
}

output "instance_private_ip" {
  description = "Private IP address of the instance"
  value       = aws_instance.leviathan_k3s.private_ip
}

output "instance_public_ip" {
  description = "Public IP address of the instance (if in public subnet)"
  value       = aws_instance.leviathan_k3s.public_ip
}

output "elastic_ip" {
  description = "Elastic IP address (if enabled)"
  value       = var.enable_elastic_ip ? aws_eip.leviathan_k3s[0].public_ip : null
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.leviathan_k3s.id
}

output "iam_role_arn" {
  description = "IAM role ARN"
  value       = aws_iam_role.leviathan_k3s.arn
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh ubuntu@${var.enable_elastic_ip ? aws_eip.leviathan_k3s[0].public_ip : aws_instance.leviathan_k3s.public_ip}"
}
