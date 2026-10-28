from __future__ import annotations

import asyncio


async def probe_tcp(host: str, port: int, *, timeout: float = 1.0) -> bool:
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(str(host), int(port)), timeout)
    except Exception:
        return False
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
    return True
