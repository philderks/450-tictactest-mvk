"""Offline contract for reusing the existing Learner Lab instance profile."""
from pathlib import Path
import unittest


INFRA = Path(__file__).resolve().parents[1]


class InstanceProfileConfigTests(unittest.TestCase):
    def test_existing_lab_profile_is_attached_without_creating_iam_resources(self):
        path = INFRA / "instance-profile.tf"
        self.assertTrue(path.is_file(), "The existing LabInstanceProfile data source is missing")
        profile = path.read_text()
        self.assertIn('data "aws_iam_instance_profile" "lab"', profile)
        self.assertRegex(profile, r'\bname\s*=\s*"LabInstanceProfile"')
        main = (INFRA / "main.tf").read_text()
        self.assertRegex(main, r'\biam_instance_profile\s*=\s*data\.aws_iam_instance_profile\.lab\.name\b')
        for source in INFRA.glob("*.tf"):
            self.assertNotRegex(source.read_text(), r'resource\s+"aws_iam_', source.name)
        outputs = (INFRA / "outputs.tf").read_text()
        for name in ("instance_profile_name", "instance_profile_role"):
            self.assertIn('output "' + name + '"', outputs)


if __name__ == "__main__":
    unittest.main()
