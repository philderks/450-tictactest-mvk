# Das Learner Lab stellt Profil und Rolle bereit; wir erstellen keine IAM-Ressourcen.
# Das Profil ist die EC2-Zuordnung, die enthaltene LabRole liefert die Berechtigungen.
data "aws_iam_instance_profile" "lab" {
  name = "LabInstanceProfile"
}
