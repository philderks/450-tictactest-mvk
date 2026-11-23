#!/usr/bin/env python3
"""Check a real, local `tofu show -json` plan without applying anything."""

import ipaddress
import json
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 infra/tests/check_plan.py PLAN.json")
    plan = json.loads(Path(sys.argv[1]).read_text())
    checks = 0

    def check(condition, message):
        nonlocal checks
        if not condition:
            raise SystemExit(f"FAIL: {message}")
        checks += 1

    changes = {
        item["address"]: item
        for item in plan.get("resource_changes", [])
        if item["mode"] == "managed"
    }
    check(
        set(changes) == {"aws_instance.server", "aws_key_pair.ssh", "aws_security_group.ssh"},
        "The initial plan must manage exactly the instance, key pair and SSH group.",
    )
    check(
        all(item["change"]["actions"] == ["create"] for item in changes.values()),
        "Only new resources may be created; no existing objects may be changed or deleted.",
    )
    server = changes["aws_instance.server"]["change"]["after"]
    group = changes["aws_security_group.ssh"]["change"]["after"]
    key = changes["aws_key_pair.ssh"]["change"]["after"]
    check(server["instance_type"] in {"t2.micro", "t3.micro"}, "Use a micro instance.")
    check(server["associate_public_ip_address"] is True, "SSH needs a public endpoint.")
    check(server["metadata_options"][0]["http_tokens"] == "required", "Require IMDSv2.")
    disk = server["root_block_device"][0]
    check(disk["encrypted"] is True, "Encrypt the root disk.")
    check(disk["delete_on_termination"] is True, "Remove the root disk with the instance.")
    check(disk["volume_size"] == 8 and disk["volume_type"] == "gp3", "Use a small gp3 root disk.")
    check(server["credit_specification"][0]["cpu_credits"] == "standard", "Avoid unlimited CPU surplus credits.")
    rules = group["ingress"]
    check(len(rules) == 1, "Allow exactly one incoming rule.")
    rule = rules[0]
    check(
        rule["protocol"] == "tcp" and rule["from_port"] == rule["to_port"] == 22,
        "Only incoming TCP/22 may be allowed.",
    )
    check(len(rule["cidr_blocks"]) == 1, "Allow only one SSH source.")
    network = ipaddress.ip_network(rule["cidr_blocks"][0], strict=True)
    check(network.version == 4 and network.prefixlen == 32, "SSH must be limited to one IPv4 address (/32).")
    check(
        not rule["ipv6_cidr_blocks"]
        and not rule["prefix_list_ids"]
        and not rule["security_groups"]
        and not rule["self"],
        "No additional incoming sources may be allowed.",
    )
    check(key["public_key"].startswith("ssh-ed25519 "), "Import only the own public SSH key.")
    # Already-read data sources are in prior_state in this OpenTofu plan JSON.
    # Planned managed resources are in planned_values; use both, with planned
    # values taking precedence if an address occurs in both sections.
    values = {}
    for section in (
        plan.get("prior_state", {}).get("values", {}),
        plan.get("planned_values", {}),
    ):
        for item in section.get("root_module", {}).get("resources", []):
            values[item["address"]] = item["values"]
    check(server["ami"] == values["data.aws_ami.server"]["id"], "Use the verified Amazon AMI.")
    check(server["subnet_id"] == values["data.aws_subnet.selected"]["id"], "Reuse the selected existing subnet.")
    check(group["vpc_id"] == values["data.aws_vpc.default"]["id"], "Reuse the existing VPC.")
    config = {item["address"]: item for item in plan["configuration"]["root_module"]["resources"]}
    expressions = config["aws_instance.server"]["expressions"]
    check(
        "aws_key_pair.ssh.key_name" in expressions["key_name"]["references"],
        "The instance must depend on the own key-pair resource.",
    )
    check(
        "aws_security_group.ssh.id" in expressions["vpc_security_group_ids"]["references"],
        "The instance must use the restricted SSH group.",
    )
    check(
        {"instance_id", "public_ip"} <= set(plan["configuration"]["root_module"]["outputs"]),
        "Expose the instance ID and public IP as outputs.",
    )
    print(f"PASS: {checks} checks on the real initial infrastructure plan; nothing applied.")


if __name__ == "__main__":
    main()
