from unittest.mock import Mock, patch

import pytest
import requests
import typer

from ai_assistant.commands.automation.docker_hub_runner import (
    DockerHubTagState,
    fetch_fixed_tag_state,
    fetch_latest_tag_state,
    parse_image,
)


def test_parse_image_defaults_to_library_namespace():
    assert parse_image("nginx") == ("library", "nginx")


def test_parse_image_returns_explicit_namespace_and_repository():
    assert parse_image("bitnami/redis") == ("bitnami", "redis")


def test_parse_image_rejects_invalid_image_name():
    with pytest.raises(typer.BadParameter, match="镜像名称格式不正确"):
        parse_image("a/b/c")


@patch("ai_assistant.commands.automation.docker_hub_runner.requests.get")
def test_fetch_latest_tag_state_returns_latest_state(mock_get: Mock):
    response = Mock()
    response.json.return_value = {
        "results": [
            {
                "name": "latest",
                "last_updated": "2026-03-10T10:00:00.000000Z",
                "images": [
                    {"digest": ""},
                    {"digest": "sha256:abc123"},
                ],
            }
        ]
    }
    mock_get.return_value = response

    state = fetch_latest_tag_state("library", "nginx", timeout=5.0)

    assert state == DockerHubTagState(
        namespace="library",
        repository="nginx",
        tag="latest",
        digest="sha256:abc123",
        last_updated="2026-03-10T10:00:00.000000Z",
    )
    mock_get.assert_called_once_with(
        "https://hub.docker.com/v2/namespaces/library/repositories/nginx/tags",
        params={"page_size": 1, "ordering": "last_updated"},
        timeout=5.0,
    )
    response.raise_for_status.assert_called_once_with()


@patch("ai_assistant.commands.automation.docker_hub_runner.requests.get")
def test_fetch_latest_tag_state_raises_when_no_results(mock_get: Mock):
    response = Mock()
    response.json.return_value = {"results": []}
    mock_get.return_value = response

    with pytest.raises(RuntimeError, match="未找到镜像标签: library/nginx"):
        fetch_latest_tag_state("library", "nginx", timeout=5.0)

    response.raise_for_status.assert_called_once_with()


@patch("ai_assistant.commands.automation.docker_hub_runner.requests.get")
def test_fetch_fixed_tag_state_returns_fixed_tag_state(mock_get: Mock):
    response = Mock()
    response.json.return_value = {
        "name": "latest",
        "last_updated": "2026-03-10T11:00:00.000000Z",
        "images": [{"digest": "sha256:def456"}],
    }
    mock_get.return_value = response

    state = fetch_fixed_tag_state("library", "nginx", "latest", timeout=8.0)

    assert state == DockerHubTagState(
        namespace="library",
        repository="nginx",
        tag="latest",
        digest="sha256:def456",
        last_updated="2026-03-10T11:00:00.000000Z",
    )
    mock_get.assert_called_once_with(
        "https://hub.docker.com/v2/namespaces/library/repositories/nginx/tags/latest",
        timeout=8.0,
    )
    response.raise_for_status.assert_called_once_with()


def test_fetch_fixed_tag_state_with_real_request():
    try:
        state = fetch_fixed_tag_state("library", "nginx", "latest", timeout=10.0)
    except requests.RequestException as exc:
        pytest.fail(f"Docker Hub 真实请求失败: {exc}")

    assert state.namespace == "library"
    assert state.repository == "nginx"
    assert state.tag == "latest"
    assert state.last_updated
    assert state.digest.startswith("sha256:")
