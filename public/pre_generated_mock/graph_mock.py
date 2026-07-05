"""GraphService 预生成 Mock。

实现 public/interface_stub/graph_service.pyi 的全部签名，
返回符合 GraphNode/GraphEdge 结构的模拟值。
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


def _iso_now() -> str:
    return datetime.now().isoformat()


def _make_node(
    node_type: str,
    properties: Optional[Dict[str, Any]] = None,
    text_content: Optional[str] = None,
    agent_id: str = "default",
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": node_type,
        "properties": properties or {},
        "text_content": text_content,
        "vector_id": None,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "agent_id": agent_id,
    }


def _make_edge(
    source_id: str,
    target_id: str,
    relation_type: str,
    properties: Optional[Dict[str, Any]] = None,
    text_content: Optional[str] = None,
    agent_id: str = "default",
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "properties": properties or {},
        "text_content": text_content,
        "vector_id": None,
        "created_at": _iso_now(),
        "agent_id": agent_id,
    }


class MockGraphService:
    """GraphService 的 Mock 实现。内存态。"""

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[str, Dict[str, Any]] = {}

    async def create_node(self, request: Dict[str, Any], agent_id: str = "default") -> Dict[str, Any]:
        if not request.get("type"):
            raise ValueError("type 不能为空")
        node = _make_node(request["type"], request.get("properties"), request.get("text_content"), agent_id)
        self._nodes[node["id"]] = node
        return dict(node)

    async def get_node(self, node_id: str, agent_id: str = "default") -> Optional[Dict[str, Any]]:
        n = self._nodes.get(node_id)
        return dict(n) if n else None

    async def update_node(
        self, node_id: str, request: Dict[str, Any], agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        n = self._nodes.get(node_id)
        if n is None:
            return None
        if request.get("type") is not None:
            n["type"] = request["type"]
        if request.get("properties") is not None:
            n["properties"] = request["properties"]
        if request.get("text_content") is not None:
            n["text_content"] = request["text_content"]
        n["updated_at"] = _iso_now()
        return dict(n)

    async def delete_node(
        self, node_id: str, cascade: bool = True, agent_id: str = "default"
    ) -> bool:
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        if cascade:
            self._edges = {eid: e for eid, e in self._edges.items()
                           if e["source_id"] != node_id and e["target_id"] != node_id}
        return True

    async def create_edge(self, request: Dict[str, Any], agent_id: str = "default") -> Dict[str, Any]:
        sid, tid = request.get("source_id"), request.get("target_id")
        if sid not in self._nodes or tid not in self._nodes:
            raise ValueError("source_id 或 target_id 不存在")
        edge = _make_edge(sid, tid, request["relation_type"], request.get("properties"),
                          request.get("text_content"), agent_id)
        self._edges[edge["id"]] = edge
        return dict(edge)

    async def get_edge(self, edge_id: str, agent_id: str = "default") -> Optional[Dict[str, Any]]:
        e = self._edges.get(edge_id)
        return dict(e) if e else None

    async def update_edge(
        self, edge_id: str, request: Dict[str, Any], agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        e = self._edges.get(edge_id)
        if e is None:
            return None
        if request.get("relation_type") is not None:
            e["relation_type"] = request["relation_type"]
        if request.get("properties") is not None:
            e["properties"] = request["properties"]
        return dict(e)

    async def delete_edge(self, edge_id: str, agent_id: str = "default") -> bool:
        if edge_id not in self._edges:
            return False
        del self._edges[edge_id]
        return True

    async def traverse_bfs(
        self, start_id: str, max_depth: int = 10,
        node_type_filter: Optional[str] = None, agent_id: str = "default",
    ) -> Dict[str, Any]:
        if start_id not in self._nodes:
            raise KeyError(f"起点不存在: {start_id}")
        visited = []
        queue = [(start_id, 0)]
        seen = {start_id}
        while queue:
            nid, depth = queue.pop(0)
            if depth > max_depth:
                continue
            node = self._nodes.get(nid)
            if node and (node_type_filter is None or node["type"] == node_type_filter):
                visited.append(dict(node))
            for e in self._edges.values():
                other = e["target_id"] if e["source_id"] == nid else (e["source_id"] if e["target_id"] == nid else None)
                if other and other not in seen:
                    seen.add(other)
                    queue.append((other, depth + 1))
        return {"nodes": visited, "edges": [], "visited_count": len(visited)}

    async def traverse_dfs(
        self, start_id: str, max_depth: int = 10,
        node_type_filter: Optional[str] = None, agent_id: str = "default",
    ) -> Dict[str, Any]:
        if start_id not in self._nodes:
            raise KeyError(f"起点不存在: {start_id}")
        visited = []
        seen = {start_id}

        def _dfs(nid: str, depth: int) -> None:
            if depth > max_depth:
                return
            node = self._nodes.get(nid)
            if node and (node_type_filter is None or node["type"] == node_type_filter):
                visited.append(dict(node))
            for e in self._edges.values():
                other = e["target_id"] if e["source_id"] == nid else (e["source_id"] if e["target_id"] == nid else None)
                if other and other not in seen:
                    seen.add(other)
                    _dfs(other, depth + 1)

        _dfs(start_id, 0)
        return {"nodes": visited, "edges": [], "visited_count": len(visited)}

    async def shortest_path(
        self, start_id: str, end_id: str, max_length: int = 10, agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        if start_id not in self._nodes or end_id not in self._nodes:
            raise KeyError("端点不存在")
        if start_id == end_id:
            return {"path": [start_id], "edges": [], "length": 0}
        return None

    async def semantic_search(
        self, query: str, node_type: Optional[str] = None, limit: int = 10, agent_id: str = "default",
    ) -> List[Dict[str, Any]]:
        results = []
        for n in self._nodes.values():
            if node_type and n["type"] != node_type:
                continue
            results.append({"node": dict(n), "score": 0.5})
            if len(results) >= limit:
                break
        return results
