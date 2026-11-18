output "instance_id" {
  description = "ID der von dieser Konfiguration verwalteten Lerninstanz."
  value       = aws_instance.server.id
}

output "public_ip" {
  description = "Oeffentliche IPv4 fuer SSH; ohne Elastic IP nicht dauerhaft fest."
  value       = aws_instance.server.public_ip
}
