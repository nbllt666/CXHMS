from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MCPServer:
    name: str
    command: str
    args: List[str]
    env: Dict[str, str]
    status: str = "disconnected"
    tools: List[Dict] = None
    last_check: str = None
    error: str = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "status": self.status,
            "tools": self.tools or [],
            "last_check": self.last_check,
            "error": self.error
        }


class MCPManager:
    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self._http_clients: Dict[str, httpx.AsyncClient] = {}

    async def add_server(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Dict = None
    ) -> Dict:
        server = MCPServer(
            name=name,
            command=command,
            args=args,
            env=env or {}
        )

        self.servers[name] = server
        logger.info(f"MCP服务器已添加: {name}")

        return server.to_dict()

    async def remove_server(self, name: str) -> bool:
        if name in self.servers:
            del self.servers[name]
            if name in self._http_clients:
                await self._http_clients[name].aclose()
                del self._http_clients[name]
            logger.info(f"MCP服务器已移除: {name}")
            return True
        return False

    async def list_servers(self) -> List[Dict]:
        return [s.to_dict() for s in self.servers.values()]

    async def get_tools(self, server_name: str) -> List[Dict]:
        server = self.servers.get(server_name)
        if not server:
            return []

        return server.tools or []

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict = None
    ) -> Dict:
        server = self.servers.get(server_name)
        if not server:
            return {"success": False, "error": f"服务器不存在: {server_name}"}

        if server.status != "connected":
            return {"success": False, "error": f"服务器未连接: {server_name}"}

        try:
            if server_name not in self._http_clients:
                self._http_clients[server_name] = httpx.AsyncClient(timeout=30.0)

            response = await self._http_clients[server_name].post(
                f"{server.command}/call",
                json={
                    "tool": tool_name,
                    "arguments": arguments or {}
                }
            )

            if response.status_code == 200:
                return {"success": True, "result": response.json()}
            else:
                return {"success": False, "error": f"调用失败: {response.status_code}"}

        except Exception as e:
            logger.error(f"MCP工具调用失败: {e}")
            return {"success": False, "error": str(e)}

    def get_stats(self) -> Dict:
        return {
            "total_servers": len(self.servers),
            "connected_servers": sum(1 for s in self.servers.values() if s.status == "connected"),
            "disconnected_servers": sum(1 for s in self.servers.values() if s.status == "disconnected"),
            "servers": [s.name for s in self.servers.values()]
        }

    async def close(self):
        for client in self._http_clients.values():
            await client.aclose()
        self._http_clients.clear()
        self.servers.clear()
        logger.info("MCP管理器已关闭")
