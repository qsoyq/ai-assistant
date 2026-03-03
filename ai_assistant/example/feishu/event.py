# 在 Dify workflow 通过 requests 请求 订阅云文档事件接口


from typing import TypedDict, cast
from urllib.parse import urlparse

import requests


class Response(TypedDict):
    status_code: int
    text: str


def get_file_token_if_url(file_token: str) -> str:
    """
    https://xxx.feishu.cn/drive/folder/xxxxx
    """
    parsed = urlparse(file_token)
    if not (parsed.scheme and parsed.netloc):
        return file_token

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 3 and path_parts[0] == "drive" and path_parts[1] == "folder":
        return path_parts[-1]

    return file_token


def add_subscription_event(file_token: str, token: str) -> Response:
    file_token = get_file_token_if_url(file_token)
    url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/subscribe"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    params = {
        "file_type": "folder",
        "event_type": "file.created_in_folder_v1",
    }
    response = requests.post(url, headers=headers, params=params)

    return Response(status_code=response.status_code, text=response.text)


def get_tenant_access_token(appid: str, appsecret: str) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }
    data = {
        "app_id": appid,
        "app_secret": appsecret,
    }
    response = requests.post(url, headers=headers, json=data)
    return cast(str, response.json()["tenant_access_token"])


def main(file_token: str, appid: str, appsecret: str):
    token = get_tenant_access_token(appid, appsecret)
    resp = add_subscription_event(file_token, token)
    text = f"添加订阅失败, status_code: {resp['status_code']}, reason: {resp['text']}" if resp["status_code"] != 200 else "添加订阅成功"
    return {
        "status_code": resp["status_code"],
        "text": text,
    }
