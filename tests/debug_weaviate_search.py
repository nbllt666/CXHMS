"""Debug Weaviate semantic search for memory_id=1388."""
import requests
import json

WEAVIATE_URL = "http://localhost:8090"
EMBEDDING_URL = "http://localhost:8101/v1/embeddings"

# 1. Check if memory_id=1388 exists in Weaviate
print("=" * 60)
print("1. Query Weaviate for memory_id=1388")
print("=" * 60)
graphql_query = {
    "query": '''{
      Get {
        CXHMSMemory(where: {operator: Equal, valueString: "1388", path: ["memory_id"]}) {
          memory_id
          content
          memory_type
          _additional {
            id
            vector
          }
        }
      }
    }'''
}
resp = requests.post(f"{WEAVIATE_URL}/v1/graphql", json=graphql_query, timeout=10)
result = resp.json()
print(json.dumps(result, indent=2, ensure_ascii=False))

# 2. Generate embedding for "系统功能测试"
print("\n" + "=" * 60)
print("2. Generate embedding for '系统功能测试'")
print("=" * 60)
embed_resp = requests.post(EMBEDDING_URL, json={
    "model": "Qwen3-Embedding-0.6B",
    "input": "系统功能测试"
}, timeout=10)
print(f"Status: {embed_resp.status_code}")
if embed_resp.status_code == 200:
    embed_data = embed_resp.json()
    embedding = embed_data.get("data", [{}])[0].get("embedding", [])
    print(f"Embedding dimension: {len(embedding)}")
    print(f"First 5 values: {embedding[:5]}")

    # 3. Search Weaviate with this embedding
    print("\n" + "=" * 60)
    print("3. Search Weaviate with '系统功能测试' embedding")
    print("=" * 60)
    search_query = {
        "query": '''{
          Get {
            CXHMSMemory(
              nearVector: {
                vector: [''' + ",".join(str(x) for x in embedding) + ''']
                certainty: 0.0
              }
              limit: 5
            ) {
              memory_id
              content
              memory_type
              _additional {
                distance
                certainty
              }
            }
          }
        }'''
    }
    search_resp = requests.post(f"{WEAVIATE_URL}/v1/graphql", json=search_query, timeout=10)
    search_result = search_resp.json()
    print(json.dumps(search_result, indent=2, ensure_ascii=False))
else:
    print(f"Embedding failed: {embed_resp.text[:500]}")

# 4. Generate embedding for "系统语义搜索功能测试" (exact match)
print("\n" + "=" * 60)
print("4. Generate embedding for '系统正在进行语义搜索功能的深度测试'")
print("=" * 60)
embed_resp2 = requests.post(EMBEDDING_URL, json={
    "model": "Qwen3-Embedding-0.6B",
    "input": "系统正在进行语义搜索功能的深度测试"
}, timeout=10)
if embed_resp2.status_code == 200:
    embed_data2 = embed_resp2.json()
    embedding2 = embed_data2.get("data", [{}])[0].get("embedding", [])
    print(f"Embedding dimension: {len(embedding2)}")

    # 5. Search with exact content embedding
    print("\n" + "=" * 60)
    print("5. Search Weaviate with exact content embedding")
    print("=" * 60)
    search_query2 = {
        "query": '''{
          Get {
            CXHMSMemory(
              nearVector: {
                vector: [''' + ",".join(str(x) for x in embedding2) + ''']
                certainty: 0.0
              }
              limit: 5
            ) {
              memory_id
              content
              _additional {
                distance
                certainty
              }
            }
          }
        }'''
    }
    search_resp2 = requests.post(f"{WEAVIATE_URL}/v1/graphql", json=search_query2, timeout=10)
    search_result2 = search_resp2.json()
    print(json.dumps(search_result2, indent=2, ensure_ascii=False))

print("\n" + "=" * 60)
print("Debug complete")
print("=" * 60)
