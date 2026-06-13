"""
图数据库 API 路由
"""

import json
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
from backend.dependencies import get_graph_database as _get_graph_database

router = APIRouter(tags=["graph"])




class NodeCreateRequest(BaseModel):
    type: str
    properties: Dict[str, Any] = {}
    text_content: Optional[str] = None


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


class EdgeUpdateRequest(BaseModel):
    relation_type: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    query: str
    node_type: Optional[str] = None
    limit: int = 10


class HybridSearchRequest(BaseModel):
    query: str
    node_type: Optional[str] = None
    properties_filter: Optional[Dict[str, Any]] = None
    limit: int = 10


class TraversalBFSRequest(BaseModel):
    start_id: str
    max_depth: int = 10
    node_type_filter: Optional[str] = None


class TraversalDFSRequest(BaseModel):
    start_id: str
    max_depth: int = 10
    node_type_filter: Optional[str] = None


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
    return graph.nodes.create(node_data)


@router.get("/nodes/{node_id}", response_model=Optional[GraphNode])
async def get_node(node_id: str, graph: GraphDatabase = Depends(_get_graph_database)):
    node = graph.nodes.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    return node


@router.put("/nodes/{node_id}", response_model=Optional[GraphNode])
async def update_node(node_id: str, request: NodeUpdateRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    update_data = NodeUpdate(
        type=request.type,
        properties=request.properties,
        text_content=request.text_content,
    )
    node = graph.nodes.update(node_id, update_data)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    return node


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, cascade: bool = True, graph: GraphDatabase = Depends(_get_graph_database)):
    graph.nodes.delete(node_id, cascade=cascade)
    return {"status": "ok", "message": f"节点 {node_id} 已删除"}


@router.post("/nodes/batch")
async def batch_create_nodes(requests: List[NodeCreateRequest], graph: GraphDatabase = Depends(_get_graph_database)):
    nodes_data = [
        NodeCreate(type=r.type, properties=r.properties, text_content=r.text_content)
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
):
    result = graph.nodes.search(node_type=node_type, limit=limit, offset=offset)
    return result


@router.get("/nodes/{node_id}/neighbors")
async def get_neighbors(
    node_id: str,
    graph: GraphDatabase = Depends(_get_graph_database),
    max_depth: int = Query(default=1, ge=1, le=10),
    direction: str = Query(default="both", pattern="^(outgoing|incoming|both)$"),
):
    neighbors = graph.traversal.get_neighbors(node_id, max_depth=max_depth, direction=direction)
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
        return graph.edges.create(edge_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/edges/{edge_id}", response_model=Optional[GraphEdge])
async def get_edge(edge_id: str, graph: GraphDatabase = Depends(_get_graph_database)):
    edge = graph.edges.get(edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail="边不存在")
    return edge


@router.put("/edges/{edge_id}", response_model=Optional[GraphEdge])
async def update_edge(edge_id: str, request: EdgeUpdateRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    update_data = EdgeUpdate(
        relation_type=request.relation_type,
        properties=request.properties,
        text_content=request.text_content,
    )
    edge = graph.edges.update(edge_id, update_data)
    if not edge:
        raise HTTPException(status_code=404, detail="边不存在")
    return edge


@router.delete("/edges/{edge_id}")
async def delete_edge(edge_id: str, graph: GraphDatabase = Depends(_get_graph_database)):
    graph.edges.delete(edge_id)
    return {"status": "ok", "message": f"边 {edge_id} 已删除"}


@router.get("/edges/search")
async def search_edges(
    graph: GraphDatabase = Depends(_get_graph_database),
    relation_type: Optional[str] = None,
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
):
    result = graph.edges.search(
        relation_type=relation_type,
        source_id=source_id,
        target_id=target_id,
        limit=limit,
        offset=offset,
    )
    return result


@router.post("/traverse/bfs")
async def traverse_bfs(request: TraversalBFSRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    nodes = graph.traversal.bfs_traverse(
        start_id=request.start_id,
        max_depth=request.max_depth,
        node_type_filter=request.node_type_filter,
    )
    return {"start_id": request.start_id, "nodes": [n.to_dict() if hasattr(n, 'to_dict') else n for n in nodes]}


@router.post("/traverse/dfs")
async def traverse_dfs(request: TraversalDFSRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    nodes = graph.traversal.dfs_traverse(
        start_id=request.start_id,
        max_depth=request.max_depth,
        node_type_filter=request.node_type_filter,
    )
    return {"start_id": request.start_id, "nodes": [n.to_dict() if hasattr(n, 'to_dict') else n for n in nodes]}


@router.get("/paths/shortest")
async def shortest_path(
    start_id: str,
    end_id: str,
    graph: GraphDatabase = Depends(_get_graph_database),
    max_length: int = Query(default=10, ge=1, le=50),
):
    path = graph.traversal.shortest_path(start_id, end_id, max_length)
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
):
    results = graph.hybrid.semantic_neighbors(node_id=node_id, limit=limit, depth=depth)
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
async def get_graph_stats(graph: GraphDatabase = Depends(_get_graph_database)):
    monitor = GraphMonitor(graph.db)
    return monitor.get_graph_stats()


@router.get("/algorithm/pagerank")
async def get_pagerank(
    graph: GraphDatabase = Depends(_get_graph_database),
    damping: float = Query(default=0.85, ge=0.0, le=1.0),
    max_iterations: int = Query(default=100, ge=1, le=1000),
):
    scores = graph.traversal.pagerank(damping=damping, max_iterations=max_iterations)
    return {"damping": damping, "scores": scores}


@router.get("/algorithm/important-nodes")
async def get_important_nodes(graph: GraphDatabase = Depends(_get_graph_database), limit: int = Query(default=10, ge=1, le=100)):
    nodes = graph.traversal.get_important_nodes(limit=limit)
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
):
    communities = graph.traversal.community_detection(method=method)
    return {
        "method": method,
        "communities": communities,
    }


@router.get("/algorithm/community-stats")
async def get_community_stats(
    graph: GraphDatabase = Depends(_get_graph_database),
    method: str = Query(default="lpa", pattern="^(lpa|louvain)$"),
):
    stats = graph.traversal.get_community_stats()
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


@router.post("/semantic/query-hops")
async def semantic_query_hops(request: SemanticQueryHopsRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    semantic_query_mgr = SemanticQueryManager(graph.db)
    results = semantic_query_mgr.semantic_query_with_hops(
        start_node_id=request.start_node_id,
        query=request.query,
        hops=request.hops,
        limit=request.limit,
        direction=request.direction,
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


@router.post("/semantic/path-constrained")
async def path_constrained_search(request: PathConstrainedSearchRequest, graph: GraphDatabase = Depends(_get_graph_database)):
    semantic_query_mgr = SemanticQueryManager(graph.db)
    results = semantic_query_mgr.path_constrained_semantic_search(
        start_node_id=request.start_node_id,
        end_node_id=request.end_node_id,
        query=request.query,
        max_path_length=request.max_path_length,
        limit=request.limit,
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
async def export_json(graph: GraphDatabase = Depends(_get_graph_database)):
    exporter = GraphExporter(graph.db)
    json_str = exporter.export_json()
    return {"format": "json", "data": json.loads(json_str)}


@router.get("/export/graphml")
async def export_graphml(
    graph: GraphDatabase = Depends(_get_graph_database),
    file_path: str = Query(default="graph_export.graphml"),
):
    exporter = GraphExporter(graph.db)
    exporter.export_graphml(file_path)
    return {"format": "graphml", "file_path": file_path, "status": "exported"}


@router.get("/export/dot")
async def export_dot(
    graph: GraphDatabase = Depends(_get_graph_database),
    file_path: str = Query(default="graph_export.dot"),
):
    exporter = GraphExporter(graph.db)
    exporter.export_dot(file_path)
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
