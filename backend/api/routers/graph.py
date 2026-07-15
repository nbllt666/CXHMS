"""
图数据库 API 路由
"""

import json
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from backend.core.graph import GraphDatabase, NodeManager, EdgeManager, TraversalManager, SemanticSearch
from backend.core.graph.models import (
    GraphNode, GraphEdge,
    NodeCreate, NodeUpdate, EdgeCreate, EdgeUpdate,
    SemanticSearchResult, PathResult
)
from backend.core.graph.visualization import GraphExporter
from backend.core.graph.semantic_query import SemanticQueryManager
from backend.core.graph.monitoring import GraphMonitor
from backend.dependencies import _get_or_create_graph_database

router = APIRouter(prefix="/graph", tags=["graph"])


def _get_graph_database(agent_id: str = Query("default")) -> GraphDatabase:
    """按 agent_id 解析对应图数据库实例（按需创建）。

    首次访问时通过 _get_or_create_graph_database 触发实例化与初始化，
    避免启动时全局初始化的开销，同时保证 REST API 可用。
    """
    try:
        return _get_or_create_graph_database(agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图数据库初始化失败: {e}")




class NodeCreateRequest(BaseModel):
    type: str
    properties: Dict[str, Any] = {}
    text_content: Optional[str] = None
    agent_id: str = "default"


class NodeUpdateRequest(BaseModel):
    type: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None


class EdgeCreateRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict[str, Any] = {}
    text_content: Optional[str] = None
    agent_id: str = "default"


class EdgeUpdateRequest(BaseModel):
    relation_type: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    query: str
    node_type: Optional[str] = None
    limit: int = 10
    agent_id: str = "default"


class HybridSearchRequest(BaseModel):
    query: str
    node_type: Optional[str] = None
    properties_filter: Optional[Dict[str, Any]] = None
    limit: int = 10
    agent_id: str = "default"


class TraversalBFSRequest(BaseModel):
    start_id: str
    max_depth: int = 10
    node_type_filter: Optional[str] = None
    agent_id: str = "default"


class TraversalDFSRequest(BaseModel):
    start_id: str
    max_depth: int = 10
    node_type_filter: Optional[str] = None
    agent_id: str = "default"


class ShortestPathRequest(BaseModel):
    start_id: str
    end_id: str
    max_length: int = 10


@router.post("/nodes", response_model=GraphNode)
async def create_node(request: NodeCreateRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    node_data = NodeCreate(
        type=request.type,
        properties=request.properties,
        text_content=request.text_content,
    )
    return graph.nodes.create(node_data, agent_id=request.agent_id)


@router.get("/nodes/{node_id}", response_model=Optional[GraphNode])
async def get_node(node_id: str, agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    node = graph.nodes.get(node_id, agent_id=agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    return node


@router.put("/nodes/{node_id}", response_model=Optional[GraphNode])
async def update_node(node_id: str, request: NodeUpdateRequest, agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    update_data = NodeUpdate(
        type=request.type,
        properties=request.properties,
        text_content=request.text_content,
    )
    node = graph.nodes.update(node_id, update_data, agent_id=agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    return node


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, cascade: bool = True, agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    graph.nodes.delete(node_id, cascade=cascade, agent_id=agent_id)
    return {"status": "ok", "message": f"节点 {node_id} 已删除"}


@router.post("/nodes/batch")
async def batch_create_nodes(requests: List[NodeCreateRequest], graph: GraphDatabase = Depends(_get_graph_database)):
    nodes_data = [
        NodeCreate(type=r.type, properties=r.properties, text_content=r.text_content, agent_id=r.agent_id)
        for r in requests
    ]
    nodes = graph.nodes.batch_create(nodes_data)
    return {"created": len(nodes), "nodes": nodes}


@router.get("/nodes/search")
async def search_nodes(
    graph: GraphDatabase = Depends(_get_graph_database),
    node_type: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    agent_id: str = Query("default"),
):
    result = graph.nodes.search(node_type=node_type, limit=limit, offset=offset, agent_id=agent_id)
    return result


@router.get("/nodes/{node_id}/neighbors")
async def get_neighbors(
    node_id: str,
    graph: GraphDatabase = Depends(_get_graph_database),
    max_depth: int = Query(default=1, ge=1, le=10),
    direction: str = Query(default="both", pattern="^(outgoing|incoming|both)$"),
    agent_id: str = Query("default"),
):
    neighbors = graph.traversal.get_neighbors(node_id, max_depth=max_depth, direction=direction, agent_id=agent_id)
    return {
        "node_id": node_id,
        "neighbors": [
            {"node": node.to_dict() if hasattr(node, 'to_dict') else node, "edges": [e.to_dict() if hasattr(e, 'to_dict') else e for e in edges]}
            for node, edges in neighbors
        ]
    }


@router.post("/edges", response_model=GraphEdge)
async def create_edge(request: EdgeCreateRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    edge_data = EdgeCreate(
        source_id=request.source_id,
        target_id=request.target_id,
        relation_type=request.relation_type,
        properties=request.properties,
        text_content=request.text_content,
    )
    try:
        return graph.edges.create(edge_data, agent_id=request.agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/edges/{edge_id}", response_model=Optional[GraphEdge])
async def get_edge(edge_id: str, agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    edge = graph.edges.get(edge_id, agent_id=agent_id)
    if not edge:
        raise HTTPException(status_code=404, detail="边不存在")
    return edge


@router.put("/edges/{edge_id}", response_model=Optional[GraphEdge])
async def update_edge(edge_id: str, request: EdgeUpdateRequest, agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    update_data = EdgeUpdate(
        relation_type=request.relation_type,
        properties=request.properties,
        text_content=request.text_content,
    )
    edge = graph.edges.update(edge_id, update_data, agent_id=agent_id)
    if not edge:
        raise HTTPException(status_code=404, detail="边不存在")
    return edge


@router.delete("/edges/{edge_id}")
async def delete_edge(edge_id: str, agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    graph.edges.delete(edge_id, agent_id=agent_id)
    return {"status": "ok", "message": f"边 {edge_id} 已删除"}


@router.get("/edges/search")
async def search_edges(
    graph: GraphDatabase = Depends(_get_graph_database),
    relation_type: Optional[str] = None,
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    agent_id: str = Query("default"),
):
    result = graph.edges.search(
        relation_type=relation_type,
        source_id=source_id,
        target_id=target_id,
        limit=limit,
        offset=offset,
        agent_id=agent_id,
    )
    return result


@router.post("/traverse/bfs")
async def traverse_bfs(request: TraversalBFSRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    nodes = graph.traversal.bfs_traverse(
        start_id=request.start_id,
        max_depth=request.max_depth,
        node_type_filter=request.node_type_filter,
        agent_id=request.agent_id,
    )
    return {"start_id": request.start_id, "nodes": [n.to_dict() if hasattr(n, 'to_dict') else n for n in nodes]}


@router.post("/traverse/dfs")
async def traverse_dfs(request: TraversalDFSRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    nodes = graph.traversal.dfs_traverse(
        start_id=request.start_id,
        max_depth=request.max_depth,
        node_type_filter=request.node_type_filter,
        agent_id=request.agent_id,
    )
    return {"start_id": request.start_id, "nodes": [n.to_dict() if hasattr(n, 'to_dict') else n for n in nodes]}


@router.get("/paths/shortest")
async def shortest_path(
    start_id: str,
    end_id: str,
    graph: GraphDatabase = Depends(_get_graph_database),
    max_length: int = Query(default=10, ge=1, le=50),
    agent_id: str = Query("default"),
):
    path = graph.traversal.shortest_path(start_id, end_id, max_length, agent_id=agent_id)
    if not path:
        raise HTTPException(status_code=404, detail="路径不存在")
    return {
        "start_id": start_id,
        "end_id": end_id,
        "path": path.path,
        "length": path.length,
        "edges": [e.to_dict() if hasattr(e, 'to_dict') else e for e in path.edges],
    }


@router.post("/semantic/search")
async def semantic_search(request: SemanticSearchRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    results = graph.semantic.search(
        query=request.query,
        node_type=request.node_type,
        limit=request.limit,
        agent_id=request.agent_id,
    )
    return {
        "query": request.query,
        "results": [
            {
                "node_id": r.node_id if hasattr(r, 'node_id') else r.get('node_id'),
                "node_type": r.node_type if hasattr(r, 'node_type') else r.get('node_type'),
                "text_content": r.text_content if hasattr(r, 'text_content') else r.get('text_content'),
                "score": r.score if hasattr(r, 'score') else r.get('score', 0),
            }
            for r in results
        ]
    }


@router.post("/semantic/hybrid")
async def hybrid_search(request: HybridSearchRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    results = graph.hybrid.filtered_semantic_search(
        query=request.query,
        node_type=request.node_type,
        properties_filter=request.properties_filter,
        limit=request.limit,
        agent_id=request.agent_id,
    )
    return {
        "query": request.query,
        "results": [
            {
                "node_id": r.node_id if hasattr(r, 'node_id') else r.get('node_id'),
                "node_type": r.node_type if hasattr(r, 'node_type') else r.get('node_type'),
                "text_content": r.text_content if hasattr(r, 'text_content') else r.get('text_content'),
                "score": r.score if hasattr(r, 'score') else r.get('score', 0),
            }
            for r in results
        ]
    }


@router.get("/semantic/neighbors/{node_id}")
async def semantic_neighbors(
    node_id: str,
    graph: GraphDatabase = Depends(_get_graph_database),
    limit: int = Query(default=10, ge=1, le=50),
    depth: int = Query(default=1, ge=1, le=5),
    agent_id: str = Query("default"),
):
    results = graph.hybrid.semantic_neighbors(node_id=node_id, limit=limit, depth=depth, agent_id=agent_id)
    return {
        "node_id": node_id,
        "results": [
            {
                "node_id": r.node_id if hasattr(r, 'node_id') else r.get('node_id'),
                "score": r.score if hasattr(r, 'score') else r.get('score', 0),
            }
            for r in results
        ]
    }


@router.get("/health")
async def health_check(graph: GraphDatabase = Depends(_get_graph_database)):
    status = graph.health_check()
    return status


@router.get("/metrics")
async def get_metrics(graph: GraphDatabase = Depends(_get_graph_database)):
    monitor = GraphMonitor(graph.db)
    return monitor.get_metrics()


@router.get("/stats")
async def get_graph_stats(agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    monitor = GraphMonitor(graph.db)
    return monitor.get_graph_stats(agent_id=agent_id)


@router.get("/algorithm/pagerank")
async def get_pagerank(
    graph: GraphDatabase = Depends(_get_graph_database),
    damping: float = Query(default=0.85, ge=0.0, le=1.0),
    max_iterations: int = Query(default=100, ge=1, le=1000),
    agent_id: str = Query("default"),
):
    scores = graph.traversal.pagerank(damping=damping, max_iterations=max_iterations, agent_id=agent_id)
    return {"damping": damping, "scores": scores}


@router.get("/algorithm/important-nodes")
async def get_important_nodes(
    graph: GraphDatabase = Depends(_get_graph_database),
    limit: int = Query(default=10, ge=1, le=100),
    agent_id: str = Query("default"),
):
    nodes = graph.traversal.get_important_nodes(limit=limit, agent_id=agent_id)
    return {
        "limit": limit,
        "nodes": [
            {
                "node": n["node"].to_dict() if hasattr(n["node"], 'to_dict') else n["node"],
                "pagerank": n["pagerank"],
            }
            for n in nodes
        ]
    }


@router.get("/algorithm/communities")
async def get_communities(
    graph: GraphDatabase = Depends(_get_graph_database),
    method: str = Query(default="lpa", pattern="^(lpa|louvain)$"),
    agent_id: str = Query("default"),
):
    communities = graph.traversal.community_detection(method=method, agent_id=agent_id)
    return {
        "method": method,
        "communities": communities,
    }


@router.get("/algorithm/community-stats")
async def get_community_stats(
    graph: GraphDatabase = Depends(_get_graph_database),
    method: str = Query(default="lpa", pattern="^(lpa|louvain)$"),
    agent_id: str = Query("default"),
):
    stats = graph.traversal.get_community_stats(agent_id=agent_id)
    return {
        "method": method,
        "stats": stats,
    }


class SemanticQueryHopsRequest(BaseModel):
    start_node_id: str
    query: str
    hops: int = 2
    limit: int = 10
    direction: str = "both"
    agent_id: str = "default"


@router.post("/semantic/query-hops")
async def semantic_query_hops(request: SemanticQueryHopsRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    semantic_query_mgr = SemanticQueryManager(graph.db)
    results = semantic_query_mgr.semantic_query_with_hops(
        start_node_id=request.start_node_id,
        query=request.query,
        hops=request.hops,
        limit=request.limit,
        direction=request.direction,
        agent_id=request.agent_id,
    )
    return {
        "start_node_id": request.start_node_id,
        "query": request.query,
        "hops": request.hops,
        "results": [
            {
                "node": r["node"].to_dict() if hasattr(r["node"], 'to_dict') else r["node"],
                "similarity": r["similarity"],
                "path": r["path"],
            }
            for r in results
        ]
    }


class PathConstrainedSearchRequest(BaseModel):
    start_node_id: str
    end_node_id: str
    query: str
    max_path_length: int = 5
    limit: int = 10
    agent_id: str = "default"


@router.post("/semantic/path-constrained")
async def path_constrained_search(request: PathConstrainedSearchRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    semantic_query_mgr = SemanticQueryManager(graph.db)
    results = semantic_query_mgr.path_constrained_semantic_search(
        start_node_id=request.start_node_id,
        end_node_id=request.end_node_id,
        query=request.query,
        max_path_length=request.max_path_length,
        limit=request.limit,
        agent_id=request.agent_id,
    )
    return {
        "start_node_id": request.start_node_id,
        "end_node_id": request.end_node_id,
        "query": request.query,
        "results": [
            {
                "node": r["node"].to_dict() if hasattr(r["node"], 'to_dict') else r["node"],
                "similarity": r["similarity"],
                "path": r["path"],
            }
            for r in results
        ]
    }


@router.get("/export/json")
async def export_json(agent_id: str = Query("default"), graph: GraphDatabase = Depends(_get_graph_database)):
    exporter = GraphExporter(graph.db)
    json_str = exporter.export_json(agent_id=agent_id)
    return {"format": "json", "data": json.loads(json_str)}


# 允许导出文件的基础目录（当前工作目录），防止路径遍历
_ALLOWED_EXPORT_DIR = os.path.abspath(".")


def _is_safe_export_path(file_path: str) -> bool:
    """验证导出路径是否位于允许的目录内，防止路径遍历攻击。"""
    abs_path = os.path.abspath(file_path)
    return abs_path == _ALLOWED_EXPORT_DIR or abs_path.startswith(_ALLOWED_EXPORT_DIR + os.sep)


@router.get("/export/graphml")
async def export_graphml(
    graph: GraphDatabase = Depends(_get_graph_database),
    file_path: str = Query(default="graph_export.graphml"),
    agent_id: str = Query("default"),
):
    if not _is_safe_export_path(file_path):
        return {"success": False, "error": "Invalid file path"}
    exporter = GraphExporter(graph.db)
    exporter.export_graphml(file_path, agent_id=agent_id)
    return {"format": "graphml", "file_path": file_path, "status": "exported"}


@router.get("/export/dot")
async def export_dot(
    graph: GraphDatabase = Depends(_get_graph_database),
    file_path: str = Query(default="graph_export.dot"),
    agent_id: str = Query("default"),
):
    if not _is_safe_export_path(file_path):
        return {"success": False, "error": "Invalid file path"}
    exporter = GraphExporter(graph.db)
    exporter.export_dot(file_path, agent_id=agent_id)
    return {"format": "dot", "file_path": file_path, "status": "exported"}


@router.get("/config")
async def get_graph_config_endpoint(graph: GraphDatabase = Depends(_get_graph_database)):
    config = graph.config
    return {
        "status": "success",
        "config": {
            "database_path": config.database_path,
            "auto_create_schema": config.auto_create_schema,
            "pool_size": config.pool_size,
            "timeout": config.timeout,
            "weaviate": {
                "url": config.weaviate.url,
                "api_key": "***" if config.weaviate.api_key else None,
                "vector_dim": config.weaviate.vector_dim,
                "batch_size": config.weaviate.batch_size,
                "ef_construction": config.weaviate.ef_construction,
                "max_connections": config.weaviate.max_connections,
            },
            "embedding": {
                "model": config.embedding.model,
                "batch_size": config.embedding.batch_size,
                "device": config.embedding.device,
                "cache_folder": config.embedding.cache_folder,
            }
        }
    }
