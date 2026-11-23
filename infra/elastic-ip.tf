# Auftrag 2, Teil 1: feste Adresse unabhaengig vom Instanz-Start/Stop.
resource "aws_eip" "server" {
  domain = "vpc"

  tags = {
    Name    = "${var.instance_name}-eip"
    Project = "TicTacTest"
  }
}

# Nur die Adresse zuordnen; die bestehende EC2 wird nicht neu erstellt.
resource "aws_eip_association" "server" {
  allocation_id       = aws_eip.server.id
  instance_id         = aws_instance.server.id
  allow_reassociation = false
}
