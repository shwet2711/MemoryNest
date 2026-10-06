# MemoryNest

MemoryNest is an AI-powered personal memory and knowledge management system.

## Project Goal

MemoryNest allows users to upload personal documents and build a searchable personal knowledge base.

Supported document types in the initial version:

- PDF
- DOCX
- TXT
- JPG
- JPEG
- PNG

## Planned Features

- User authentication
- Document upload
- PDF/DOCX/TXT text extraction
- Image OCR
- Text preprocessing
- Document chunking
- Embeddings
- Vector database
- Retrieval-Augmented Generation (RAG)
- AI chat with source references
- Conversation history
- Document summaries
- Event extraction
- Reminder support
- Knowledge graph
- Dashboard

## Technology Stack

- Python
- Streamlit
- SQLite
- SQLAlchemy
- ChromaDB
- Sentence Transformers
- Tesseract OCR
- Ollama
- Git/GitHub

## Project Status

🚧 Under Development

## Document Indexing and Semantic Retrieval

MemoryNest uses Sentence Transformers to generate vector embeddings from document chunks and ChromaDB for persistent vector storage.

### Index a document

```powershell
python -m app.scripts.index_document --document-id 6 --user-id 1
```

Replace the document and user IDs with the values in your database.

### Search documents

```powershell
python -m app.scripts.manual_search --user-id 1 --query "What is MindSync?" --top-k 5
```

### Current retrieval pipeline

1. Retrieve document chunks.
2. Generate normalized embeddings.
3. Store vectors and metadata in ChromaDB.
4. Store embedding references in SQLite.
5. Convert the user's question into an embedding.
6. Retrieve relevant chunks scoped to the user's ID.
7. Return document source information and similarity distance.

### Current limitations

* LLM-based answer generation is not yet connected.
* Search results are retrieved passages, not generated answers.
* Knowledge graph retrieval is planned.
* Event extraction and reminder integrations are planned.
