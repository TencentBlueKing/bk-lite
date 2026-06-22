"""
Tests for SSHClient host key policy — regression for Issue #3522.

Verifies that SSHClient uses RejectPolicy (not AutoAddPolicy) so that
connections to unknown SSH hosts are rejected rather than silently accepted,
preventing man-in-the-middle (MITM) attacks.

Revert-fail criterion: if the fix is reverted (AutoAddPolicy restored),
every test in this module fails.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Ensure stargazer root is importable without Sanic/Django
sys.path.insert(0, str(Path(__file__).parent.parent))

import paramiko

from core.ssh_client import SSHClient


class TestSSHClientHostKeyPolicy:
    """Verify the missing-host-key policy is RejectPolicy, never AutoAddPolicy."""

    def _get_policy(self, client: SSHClient) -> object:
        """Extract the policy object set on the underlying paramiko SSHClient."""
        return client._client._policy

    def test_default_policy_is_reject_not_auto_add(self):
        """Without known_hosts_file, policy must be RejectPolicy, not AutoAddPolicy."""
        client = SSHClient()
        policy = self._get_policy(client)
        assert not isinstance(policy, paramiko.AutoAddPolicy), (
            "AutoAddPolicy found — this allows silent MITM; must use RejectPolicy"
        )
        assert isinstance(policy, paramiko.RejectPolicy), (
            f"Expected RejectPolicy, got {type(policy).__name__}"
        )

    def test_explicit_known_hosts_file_still_uses_reject_policy(self):
        """When a known_hosts_file is supplied, unknown hosts are still rejected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix="known_hosts", delete=False) as f:
            # Empty known_hosts file — no trusted hosts
            hosts_path = f.name
        try:
            client = SSHClient(known_hosts_file=hosts_path)
            policy = self._get_policy(client)
            assert isinstance(policy, paramiko.RejectPolicy), (
                f"With known_hosts_file set, expected RejectPolicy, got {type(policy).__name__}"
            )
        finally:
            os.unlink(hosts_path)

    def test_env_var_known_hosts_file_still_uses_reject_policy(self):
        """When SSH_KNOWN_HOSTS_FILE env var is set, policy is still RejectPolicy."""
        with tempfile.NamedTemporaryFile(mode="w", suffix="known_hosts", delete=False) as f:
            hosts_path = f.name
        try:
            with patch.dict(os.environ, {"SSH_KNOWN_HOSTS_FILE": hosts_path}):
                client = SSHClient()
            policy = self._get_policy(client)
            assert isinstance(policy, paramiko.RejectPolicy), (
                f"With SSH_KNOWN_HOSTS_FILE env var, expected RejectPolicy, got {type(policy).__name__}"
            )
        finally:
            os.unlink(hosts_path)

    def test_no_env_var_no_known_hosts_file_uses_reject_policy(self):
        """With neither env var nor explicit file, policy is RejectPolicy."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SSH_KNOWN_HOSTS_FILE", None)
            client = SSHClient()
        policy = self._get_policy(client)
        assert isinstance(policy, paramiko.RejectPolicy)

    def test_auto_add_policy_would_fail_this_test(self):
        """Demonstrate that AutoAddPolicy is detectable — ensures revert-fail property."""
        # Construct a raw paramiko client with AutoAddPolicy to confirm detection works
        raw = paramiko.SSHClient()
        raw.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        assert isinstance(raw._policy, paramiko.AutoAddPolicy), (
            "Sanity check: AutoAddPolicy should be detectable on raw paramiko client"
        )
        # SSHClient must NOT produce this
        our_client = SSHClient()
        assert not isinstance(self._get_policy(our_client), paramiko.AutoAddPolicy)
