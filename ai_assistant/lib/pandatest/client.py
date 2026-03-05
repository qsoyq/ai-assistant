import logging
from typing import TypedDict

logger = logging.getLogger("pandatest.api")


RequestHeaders = TypedDict(
    "RequestHeaders",
    {
        "Authorization": str,
        "Content-Type": str,
    },
)


class PandaTestClient:
    def __init__(self, api_key: str, api_host: str):
        self.api_key = api_key
        self.api_host = api_host

    def get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
