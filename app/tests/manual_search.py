from app.services.search_service import semantic_search


query = "What is MindSync?"

results = semantic_search(
    query=query,
    user_id=1,
    top_k=5,
)

print()
print("QUERY")
print("-----")
print(query)

print()
print("RESULTS")
print("-------")

for index, result in enumerate(results, start=1):
    print()
    print(f"Result {index}")
    print("Source:", result["metadata"]["source_filename"])
    print("Chunk ID:", result["metadata"]["chunk_id"])
    print("Chunk Index:", result["metadata"]["chunk_index"])
    print("Distance:", result["distance"])
    print("Content:")
    print(result["content"][:500])