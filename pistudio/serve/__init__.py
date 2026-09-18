"""Prompt Injection Studio — payload hosting server and utilities.

This package provides:
- PayloadServer: HTTP/HTTPS server for hosting prompt injection payloads
- PayloadRegistry: Ephemeral in-memory registry for hosted payloads
- NgrokTunnel: ngrok tunnel for public URL exposure
- Request logging for tracking model access
- URL generation utilities for short slugs
"""

from pistudio.serve.registry import (
    HostedPayload,
    PayloadRegistry,
    get_registry,
)
from pistudio.serve.server import (
    PayloadServer,
    RequestLog,
    clear_request_log,
    get_request_log,
    get_server_status,
)
from pistudio.serve.tunnel import (
    NgrokTunnel,
    TunnelInfo,
    get_tunnel_status,
    stop_active_tunnel,
)

__all__ = [
    "HostedPayload",
    "NgrokTunnel",
    "PayloadRegistry",
    "PayloadServer",
    "RequestLog",
    "TunnelInfo",
    "clear_request_log",
    "get_registry",
    "get_request_log",
    "get_server_status",
    "get_tunnel_status",
    "stop_active_tunnel",
]
