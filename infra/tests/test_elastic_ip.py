"""Offline contracts for the fixed-address infrastructure slice (no AWS writes)."""
from pathlib import Path
import re
import unittest


INFRA = Path(__file__).resolve().parents[1]


class ElasticIPConfigTests(unittest.TestCase):
    def test_fixed_address_is_associated_with_existing_instance(self):
        path = INFRA / "elastic-ip.tf"
        self.assertTrue(path.is_file(), "The fixed-address configuration is missing")
        text = path.read_text()
        for expression in (
            'resource "aws_eip" "server"',
            'domain = "vpc"',
            'resource "aws_eip_association" "server"',
            'allocation_id       = aws_eip.server.id',
            'instance_id         = aws_instance.server.id',
            'allow_reassociation = false',
        ):
            self.assertIn(expression, text)

    def test_public_ip_output_uses_the_associated_elastic_address(self):
        text = (INFRA / "outputs.tf").read_text()
        match = re.search(r'output "public_ip"\s*\{([^}]+)\}', text)
        assert match is not None, "The public_ip output is missing"
        block = match.group(1)
        self.assertIn("aws_eip.server.public_ip", block)
        self.assertIn("depends_on", block)
        self.assertIn("aws_eip_association.server", block)
        self.assertIn('output "elastic_ip_allocation_id"', text)


if __name__ == "__main__":
    unittest.main()
