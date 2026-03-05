import uuid

import typer

from ai_assistant.commands import default_invoke_without_command
from ai_assistant.lib.pandatest.device import Device, PandaTestDevice

helptext = """
PandaTest云测试平台功能验证 PoC.

https://www.pandatest.net/
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def filter_devices(devices: list[Device]) -> list[Device]:
    return [x for x in devices if x.is_available]


@cmd.command()
def poc(api_key: str = typer.Option(..., help="API Key"), api_host: str = typer.Option(..., help="API Host")):
    """
    查询、占用、心跳、释放设备

    测试设备管理相关 API 需要符合预期
    """
    api = PandaTestDevice(api_key, api_host)
    # 查询设备
    devices = api.get_devices().data

    # 过滤设备
    devices = filter_devices(devices)
    if not devices:
        typer.echo("No devices found")
        return

    # 锁定全部设备, 如果存在锁定失败的，则释放已锁定的, 然后退出
    success: list[Device] = []
    failed: list[Device] = []
    for device in devices:
        res = api.acquire_device(device.id, str(uuid.uuid4()))
        if res.success:
            success.append(device)
        else:
            failed.append(device)
    # 部分锁定成功, 部分锁定失败, 则释放已锁定的, 然后退出
    if failed:
        for device in success:
            release_res = api.release_device(device.id, str(uuid.uuid4()))
            assert release_res.success, f"Failed to release device: {device.id}"
        typer.echo(f"Failed to lock devices: {failed}")
        raise typer.Exit(1)

    # 全部锁定成功, 接下来释放设备
    typer.echo(f"Locked devices: {[x.name for x in success]}")
    for device in success:
        release_res = api.release_device(device.id, str(uuid.uuid4()))
        if release_res.success:
            typer.echo(f"Released device: {device.name}")
        else:
            typer.echo(f"Failed to release device: {device.name}")
            raise typer.Exit(1)


if __name__ == "__main__":
    cmd()
