"""macOS PF_ROUTE routing-socket helpers for RTF_GLOBAL routes.

`route(8)` 无法设置 RTF_GLOBAL (0x40000000)。部分 VPN 客户端 (如 Tailscale 开启
accept-routes) 会安装 RTF_IFSCOPE|RTF_GLOBAL 的子网路由并遮蔽物理网卡直连路由,
导致经 `route(8)` 添加的路由可能被内核打上 IFSCOPE, 在全局路由查找中不被选中。
本模块通过 PF_ROUTE socket 直接下发 RTM_ADD/RTM_DELETE 消息并请求 RTF_GLOBAL。
实测 (macOS 15/Darwin 25) 内核会忽略非 scoped 路由上的 RTF_GLOBAL 标志; 实际
生效的是路由以非 scoped 形式安装, 从而按最长前缀参与全局查找并战胜 VPN 的
scoped 子网路由。仅支持 IPv4。
"""

from __future__ import annotations

import ipaddress
import socket
import struct

RTM_VERSION = 5
RTM_ADD = 0x1
RTM_DELETE = 0x2

RTF_UP = 0x1
RTF_GATEWAY = 0x2
RTF_STATIC = 0x800
RTF_GLOBAL = 0x40000000

RTA_DST = 0x1
RTA_GATEWAY = 0x2
RTA_NETMASK = 0x4

# typeshed 仅在 darwin 上定义 socket.AF_ROUTE; 常量兜底保证其他平台 import 安全。
_AF_ROUTE = getattr(socket, "AF_ROUTE", 17)

# rt_msghdr (net/route.h): msglen, version, type, index, [2 pad], flags, addrs,
# pid, seq, errno, use, inits; 之后是 56 字节的 struct rt_metrics (全零)。
_RT_MSGHDR_FMT = "=HBBH2xiiiiiiI"
_RT_MSGHDR_SIZE = struct.calcsize(_RT_MSGHDR_FMT)
_RT_METRICS_SIZE = 56
_HEADER_SIZE = _RT_MSGHDR_SIZE + _RT_METRICS_SIZE
assert _RT_MSGHDR_SIZE == 36, "unexpected rt_msghdr layout drift"
assert _HEADER_SIZE == 92

_ROUTE_FLAGS = RTF_UP | RTF_GATEWAY | RTF_STATIC | RTF_GLOBAL
_ROUTE_ADDRS = RTA_DST | RTA_GATEWAY | RTA_NETMASK

ROUTE_FLAGS_LABEL = "UP,GATEWAY,STATIC,GLOBAL"


def pack_sockaddr_in(ip: str) -> bytes:
    """Pack a 16-byte sa_len-prefixed sockaddr_in (already 4-byte aligned)."""
    return struct.pack("=BBH4s8x", 16, socket.AF_INET, 0, socket.inet_aton(ip))


def build_route_message(msg_type: int, dest: str, gateway: str, seq: int, pid: int) -> bytes:
    network = ipaddress.ip_network(dest, strict=False)
    if network.version != 4:
        raise ValueError("PF_ROUTE RTF_GLOBAL messages only support IPv4")
    payload = pack_sockaddr_in(str(network.network_address)) + pack_sockaddr_in(gateway) + pack_sockaddr_in(str(network.netmask))
    msglen = _HEADER_SIZE + len(payload)
    header = struct.pack(_RT_MSGHDR_FMT, msglen, RTM_VERSION, msg_type, 0, _ROUTE_FLAGS, _ROUTE_ADDRS, pid, seq, 0, 0, 0)
    return header + b"\x00" * _RT_METRICS_SIZE + payload


def parse_route_ack(data: bytes) -> tuple[int, int, int]:
    """Return (rtm_type, rtm_seq, rtm_errno) from a routing message header."""
    _msglen, _version, rtm_type, _index, _flags, _addrs, _pid, rtm_seq, rtm_errno, _use, _inits = struct.unpack_from(_RT_MSGHDR_FMT, data)
    return rtm_type, rtm_seq, rtm_errno


def send_route_message(message: bytes) -> None:
    """Write one routing message; macOS reports failures synchronously as OSError."""
    sock = socket.socket(_AF_ROUTE, socket.SOCK_RAW, 0)
    try:
        sock.send(message)
    finally:
        sock.close()
