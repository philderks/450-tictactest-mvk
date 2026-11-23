output "instance_id" {
  description = "ID der von dieser Konfiguration verwalteten Lerninstanz."
  value       = aws_instance.server.id
}

output "public_ip" {
  description = "Feste Elastic IPv4 fuer SSH; bleibt bei Stop/Start zugeordnet."
  value       = aws_eip.server.public_ip
  depends_on  = [aws_eip_association.server]
}

output "elastic_ip_allocation_id" {
  description = "Allocation-ID der von OpenTofu verwalteten festen IPv4."
  value       = aws_eip.server.id
}

output "frontend_url" {
  description = "Oeffentliche HTTP-Spielseite; noch ohne TLS."
  value       = "http://${aws_eip.server.public_ip}/"
  depends_on  = [aws_eip_association.server]
}

output "console_url" {
  description = "Web-Konsole hinter dem oeffentlichen HTTP-Proxy."
  value       = "http://${aws_eip.server.public_ip}/console/"
  depends_on  = [aws_eip_association.server]
}

output "backend_version_url" {
  description = "HTTP-Versionsabfrage des ausgewaehlten Release-Jars."
  value       = "http://${aws_eip.server.public_ip}/backend-version.txt"
  depends_on  = [aws_eip_association.server]
}
