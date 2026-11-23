"""Unit tests for AutoClips AI's local-only browser request policy."""

import unittest

from backend.security import is_local_request_allowed


class LocalAccessPolicyTests(unittest.TestCase):
    def policy(self, **overrides):
        values = {
            "client_host": "127.0.0.1",
            "host_header": "127.0.0.1:8000",
            "origin": "http://127.0.0.1:8000",
            "method": "GET",
            "path": "/api/v1/health",
            "sec_fetch_site": "same-origin",
            "sec_fetch_mode": "cors",
            "sec_fetch_dest": "empty",
        }
        values.update(overrides)
        return is_local_request_allowed(**values)

    def test_same_origin_loopback_is_allowed(self):
        self.assertTrue(self.policy())

    def test_localhost_alias_is_allowed(self):
        self.assertTrue(
            self.policy(
                host_header="localhost:8000",
                origin="http://localhost:8000",
            )
        )

    def test_remote_client_is_rejected_even_with_loopback_host_header(self):
        self.assertFalse(self.policy(client_host="192.168.1.20"))

    def test_remote_or_dns_rebinding_host_is_rejected(self):
        self.assertFalse(
            self.policy(host_header="attacker.example:8000", origin="http://attacker.example:8000")
        )

    def test_cross_origin_browser_request_is_rejected(self):
        self.assertFalse(self.policy(origin="http://evil.example"))

    def test_origin_port_must_match_host_port(self):
        self.assertFalse(self.policy(origin="http://127.0.0.1:9000"))

    def test_cross_site_top_level_dashboard_navigation_is_allowed(self):
        self.assertTrue(
            self.policy(
                origin=None,
                method="GET",
                path="/",
                sec_fetch_site="cross-site",
                sec_fetch_mode="navigate",
                sec_fetch_dest="document",
            )
        )

    def test_cross_site_api_request_is_rejected(self):
        self.assertFalse(
            self.policy(
                origin=None,
                path="/api/v1/health",
                sec_fetch_site="cross-site",
                sec_fetch_mode="cors",
                sec_fetch_dest="empty",
            )
        )

    def test_cross_site_static_subresource_is_rejected(self):
        self.assertFalse(
            self.policy(
                origin=None,
                path="/app.js",
                sec_fetch_site="cross-site",
                sec_fetch_mode="no-cors",
                sec_fetch_dest="script",
            )
        )

    def test_cross_site_post_is_rejected(self):
        self.assertFalse(
            self.policy(
                origin=None,
                method="POST",
                path="/",
                sec_fetch_site="cross-site",
                sec_fetch_mode="navigate",
                sec_fetch_dest="document",
            )
        )


if __name__ == "__main__":
    unittest.main()
