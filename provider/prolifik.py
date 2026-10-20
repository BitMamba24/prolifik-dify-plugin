from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from prolifik_api.client import ProlifikClient, ProlifikError
from prolifik_api.tooling import CREDENTIAL_KEY


class ProlifikProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # GET /usage is the cheapest call that proves the key: it needs a valid,
        # unexpired key with content:read and touches no media. The Zapier
        # integration tests its connection the same way.
        try:
            ProlifikClient(credentials.get(CREDENTIAL_KEY, "")).get("/usage")
        except ProlifikError as err:
            raise ToolProviderCredentialValidationError(str(err)) from err
