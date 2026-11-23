variable "aws_region" {
  description = "AWS-Region fuer das Learner Lab. Vor einem Wechsel die Lab-Vorgaben pruefen."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Zone des bestehenden Standard-Subnetzes; muss zur gewaehlten Region passen."
  type        = string
  default     = "us-east-1a"
}

variable "instance_name" {
  description = "Name fuer die Lerninstanz und ihre eigenen SSH-Ressourcen."
  type        = string
  default     = "tictactest-iac"
}

variable "instance_type" {
  description = "Kleine EC2-Instanz fuer den Grundauftrag."
  type        = string
  default     = "t3.micro"

  validation {
    condition     = contains(["t2.micro", "t3.micro"], var.instance_type)
    error_message = "Fuer diesen Lernschritt sind nur t2.micro und t3.micro vorgesehen."
  }
}

variable "ami_id" {
  description = "Vorab gepruefte Amazon-Linux-AMI in der gewaehlten Region."
  type        = string

  validation {
    condition     = can(regex("^ami-([0-9a-f]{8}|[0-9a-f]{17})$", var.ami_id))
    error_message = "ami_id muss eine unveraenderte, gueltig formatierte AMI-ID sein."
  }
}

variable "ssh_public_key_path" {
  description = "Pfad zum eigenen oeffentlichen Ed25519-Schluessel ausserhalb des Repositorys."
  type        = string

  validation {
    condition     = can(regex("^ssh-ed25519 ", file(pathexpand(var.ssh_public_key_path))))
    error_message = "Der Pfad muss auf eine lesbare oeffentliche Ed25519-.pub-Datei zeigen, nicht auf den privaten Schluessel."
  }
}

variable "ssh_allowed_cidr" {
  description = "Oeffentliche IPv4-Adresse des SSH-Clients mit /32; keine weltweite Freigabe."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.ssh_allowed_cidr)) && can(regex("/32$", var.ssh_allowed_cidr))
    error_message = "SSH muss auf genau eine gueltige IPv4-Adresse mit /32 beschraenkt sein."
  }
}
