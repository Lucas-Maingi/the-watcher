"""Compliance mapping: findings -> ISO 27001 / SOC 2 control categories.

Deliberately a dumb lookup table. Compliance mapping products are a
whole industry; this layer exists so a finding can say "this is the
kind of thing your auditor will ask about under A.8.3" - it is not an
audit tool and doesn't pretend to be.
"""

from __future__ import annotations

_MAP: dict[str, list[dict[str, str]]] = {
    "wildcard_iam": [
        {"framework": "ISO 27001", "control": "A.8.2", "name": "Privileged access rights"},
        {"framework": "ISO 27001", "control": "A.8.3", "name": "Information access restriction"},
        {"framework": "SOC 2", "control": "CC6.3", "name": "Least-privilege authorization"},
    ],
    "open_security_group": [
        {"framework": "ISO 27001", "control": "A.8.20", "name": "Network security"},
        {"framework": "ISO 27001", "control": "A.8.22", "name": "Segregation of networks"},
        {"framework": "SOC 2", "control": "CC6.6", "name": "External access restriction"},
    ],
    "public_bucket": [
        {"framework": "ISO 27001", "control": "A.8.12", "name": "Data leakage prevention"},
        {"framework": "SOC 2", "control": "CC6.1", "name": "Logical access security"},
        {"framework": "SOC 2", "control": "C1.1", "name": "Confidential information protection"},
    ],
    "ci_long_lived_secret": [
        {"framework": "ISO 27001", "control": "A.8.28", "name": "Secure coding (CI/CD)"},
        {"framework": "ISO 27001", "control": "A.5.17", "name": "Authentication information"},
        {"framework": "SOC 2", "control": "CC6.1", "name": "Logical access security"},
    ],
    "single_point_of_failure": [
        {"framework": "ISO 27001", "control": "A.8.14", "name": "Redundancy of facilities"},
        {"framework": "SOC 2", "control": "A1.2", "name": "Availability - recovery"},
    ],
}


def controls_for(rule: str) -> list[dict[str, str]]:
    return list(_MAP.get(rule, []))
