# PDF Q&A Chatbot using LangChain and Open-Source Models

A Python application that builds a custom PDF Q&A chatbot using LangChain, HuggingFace embeddings, and the Qwen2.5-1.5B-Instruct LLM. All components run locally with no API keys required.

## How it works

1. PDF documents are uploaded (via web UI or CLI) and text is extracted using PyPDF2
2. Extracted text is split into 500-character chunks using `RecursiveCharacterTextSplitter`
3. Chunks are embedded using `sentence-transformers/all-MiniLM-L6-v2` and stored in a FAISS vector store
4. A conversational retrieval chain is built using LangChain with `ConversationBufferMemory`
5. User questions are answered by `Qwen/Qwen2.5-1.5B-Instruct` using relevant chunks retrieved via similarity search
6. All documents, chunks, and chat history are persisted in a SQLite database (`chatbot.db`)

## Requirements

### Prerequisites
- Python 3.10+
- NVIDIA GPU with CUDA support (recommended)

### Installation
```bash
pip install streamlit pypdf2 langchain langchain-community langchain-classic langchain-core langchain-huggingface langchain-text-splitters faiss-cpu python-dotenv sentence-transformers accelerate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

## Code Structure

- `app.py`: Streamlit web interface with Claude-style chat UI
    * `get_pdf_text`: extracts text from uploaded PDFs and stores pages in SQLite
    * `get_text_chunks`: splits text into 500-char chunks and stores in SQLite
    * `get_vectorstore`: creates a FAISS vector store using HuggingFace embeddings
    * `get_conversation_chain`: loads Qwen2.5-1.5B-Instruct and creates a retrieval chain
- `cli.py`: Command-line driver for terminal-based Q&A (type `exit` to quit)
- `db.py`: SQLite database module with three tables: `documents`, `chunks`, `chat_history`
- `htmlTemplates.py`: HTML/CSS templates for chat message styling (legacy)

## How to run

### Web Interface (Streamlit)
```bash
streamlit run app.py
```
1. Upload PDFs in the sidebar
2. Click "Process"
3. Ask questions in the chat input at the bottom

### CLI Driver
```bash
# Process PDFs and start Q&A
python cli.py "Ads cookbook .pdf" ads_data_html/licensing.pdf

# Use documents already stored in the database
python cli.py
```
Type your questions at the `You:` prompt. Type `exit` to quit.

## Models Used

| Component | Model | Size |
|-----------|-------|------|
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` | ~80MB |
| LLM | `Qwen/Qwen2.5-1.5B-Instruct` | ~3GB |
| LLM | `Qwen/Qwen2.5-7B-Instruct` | ~14-16GB |

Both models are downloaded automatically on first run from HuggingFace Hub.
