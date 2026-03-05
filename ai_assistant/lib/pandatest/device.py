from typing import Any

import httpx
from pydantic import BaseModel, Field

from ai_assistant.lib.pandatest.client import PandaTestClient


class AgentDetail(BaseModel):
    id: int
    agent_id: str
    name: str
    has_hub: bool
    status: str
    ip_address: str
    port: int
    rack_rows: int
    rack_columns: int
    remote_timeout: int


class Device(BaseModel):
    id: int
    os_type_display: str
    status_display: str
    tier_display: str
    is_available: bool
    success_rate: float
    group_names: list[str] = Field(default_factory=list)
    agent_name: str
    agent_unique_id: str
    agent_detail: AgentDetail
    group_details: list[dict[str, Any]] = Field(default_factory=list)
    photo_url: str | None
    device_id: str
    serialno: str
    devpath: str
    sdk: str
    name: str
    model: str
    brand: str
    nickname: str
    border_key: str
    rack_row: int | None
    rack_column: int | None
    platform: str
    version: str
    arch: str
    temperature: float
    resolution: str
    tier: str
    ip_address: str
    status: str
    last_online: str
    password: str
    total_tests: int
    success_tests: int
    failed_tests: int
    is_active: bool
    photo_object_key: str | None
    description: str
    created_at: str
    updated_at: str
    agent: int
    groups: list[int]


class Session(BaseModel):
    id: int
    session_id: str
    device_name: str
    device_id: str
    username: str
    status: str
    started_at: str
    ended_at: str | None
    client_info: dict


class AcquireDeviceData(BaseModel):
    session: Session
    device: Device


class BaseResponse(BaseModel):
    code: int
    message: str
    data: Any | None = None
    success: bool


class ReleaseDeviceResponse(BaseResponse):
    data: Device | None = None


class AcquireDeviceResponse(BaseResponse):
    data: AcquireDeviceData | None = None


class Pagination(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class ListDevicesResponse(BaseResponse):
    data: list[Device] = Field(default_factory=list)
    pagination: Pagination | None = None


class PandaTestDevice(PandaTestClient):
    def __init__(self, api_key: str, api_host: str):
        super().__init__(api_key, api_host)

    @staticmethod
    def _normalize_response(resp: httpx.Response) -> dict[str, Any]:
        try:
            payload = resp.json()
        except ValueError:
            return {
                "code": resp.status_code,
                "message": "Invalid JSON response",
                "success": False,
                "data": None,
            }

        if not isinstance(payload, dict):
            return {
                "code": resp.status_code,
                "message": "Unexpected response payload",
                "success": False,
                "data": None,
            }

        payload.setdefault("code", resp.status_code)
        payload.setdefault("message", "")
        payload.setdefault("success", resp.is_success)
        payload.setdefault("data", None)
        return payload

    def get_devices(self) -> ListDevicesResponse:
        endpoint = "/api/devices/"
        url = self.api_host + endpoint

        resp = httpx.get(url, headers=self.get_headers())
        payload = self._normalize_response(resp)
        payload.setdefault("data", [])
        payload.setdefault("pagination", None)
        return ListDevicesResponse.model_validate(payload)

    def release_device(self, device_id: int, session_id: str) -> ReleaseDeviceResponse:
        endpoint = f"/api/devices/{device_id}/release/"
        url = self.api_host + endpoint
        payload = {"session_id": session_id}
        resp = httpx.post(url, headers=self.get_headers(), json=payload)
        return ReleaseDeviceResponse.model_validate(self._normalize_response(resp))

    def acquire_device(self, device_id: int, session_id: str) -> AcquireDeviceResponse:
        endpoint = f"/api/devices/{device_id}/acquire/"
        url = self.api_host + endpoint
        payload = {"session_id": session_id}
        resp = httpx.post(url, headers=self.get_headers(), json=payload)
        return AcquireDeviceResponse.model_validate(self._normalize_response(resp))

    def heartbeat(self, session_id: str) -> BaseResponse:
        endpoint = "/api/devices/session-heartbeat/"
        url = self.api_host + endpoint
        payload = {"session_id": session_id}
        resp = httpx.post(url, headers=self.get_headers(), json=payload)
        return BaseResponse.model_validate(self._normalize_response(resp))
