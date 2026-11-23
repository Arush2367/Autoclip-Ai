import unittest
from unittest.mock import Mock, patch

from backend.services import meta_publisher


class MetaRequestSecurityTests(unittest.TestCase):
    def test_access_token_is_sent_as_authorization_header_not_url_query(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"id": "123"}
        with patch.object(meta_publisher.requests, "request", return_value=response) as request:
            result = meta_publisher.graph_request(
                "GET", "me", params={"fields": "id"}, access_token="example-secret-token"
            )
        self.assertEqual(result, {"id": "123"})
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["params"], {"fields": "id"})
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer example-secret-token"})
        self.assertNotIn("access_token", kwargs["params"])
        self.assertFalse(kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
