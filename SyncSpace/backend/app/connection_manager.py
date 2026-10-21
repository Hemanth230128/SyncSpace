import asyncio
from typing import Any
from fastapi import WebSocket


class ConnectionManager:
    """
    Manages active WebSocket connections grouped by group_id.

    Maintains an in-memory mapping of group IDs to active WebSocket client connections.
    Handles accepting connections, tracking, clean disconnects, and real-time broadcasting.
    """

    def __init__(self) -> None:
        # group_id -> list of active WebSocket connections
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, group_id: int, websocket: WebSocket) -> None:
        """
        Accepts the incoming WebSocket connection (if not already accepted) and registers it under the specified group.
        """
        from starlette.websockets import WebSocketState
        if websocket.client_state == WebSocketState.CONNECTING:
            await websocket.accept()
        if group_id not in self.active_connections:
            self.active_connections[group_id] = []
        self.active_connections[group_id].append(websocket)

    def disconnect(self, group_id: int, websocket: WebSocket) -> None:
        """
        Removes a WebSocket connection from the specified group's active list.
        Cleans up the dictionary key if no active connections remain for that group.
        """
        if group_id in self.active_connections:
            if websocket in self.active_connections[group_id]:
                self.active_connections[group_id].remove(websocket)
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]

    async def broadcast(self, group_id: int, message: dict[str, Any]) -> None:
        """
        Broadcasts a JSON message payload concurrently to all currently connected members in a group.
        Uses asyncio.gather so slow connections do not block other recipients.
        Safely removes any broken or disconnected sockets without throwing exceptions.
        """
        if group_id not in self.active_connections:
            return

        connections = list(self.active_connections[group_id])

        async def _safe_send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_json(message)
                return None
            except Exception:
                return ws

        # Fire all sends concurrently in parallel
        results = await asyncio.gather(*(_safe_send(ws) for ws in connections))
        for dead_ws in results:
            if dead_ws:
                self.disconnect(group_id, dead_ws)


# Global singleton instance for the application
manager = ConnectionManager()
