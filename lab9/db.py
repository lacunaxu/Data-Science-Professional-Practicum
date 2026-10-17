import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "chatbot.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            chunk_size INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def store_document_pages(filename, pages):
    """Store extracted PDF pages into the documents table. Returns list of doc IDs."""
    conn = get_connection()
    cur = conn.cursor()
    doc_ids = []
    for page_num, content in enumerate(pages):
        cur.execute(
            "INSERT INTO documents (filename, page_number, content) VALUES (?, ?, ?)",
            (filename, page_num + 1, content),
        )
        doc_ids.append(cur.lastrowid)
    conn.commit()
    conn.close()
    return doc_ids


def store_chunks(chunks, document_id=None):
    """Store text chunks into the chunks table."""
    conn = get_connection()
    cur = conn.cursor()
    for i, chunk in enumerate(chunks):
        cur.execute(
            "INSERT INTO chunks (document_id, chunk_index, content, chunk_size) VALUES (?, ?, ?, ?)",
            (document_id, i, chunk, len(chunk)),
        )
    conn.commit()
    conn.close()


def store_chat_message(session_id, role, message):
    """Store a chat message."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_history (session_id, role, message) VALUES (?, ?, ?)",
        (session_id, role, message),
    )
    conn.commit()
    conn.close()


def get_all_documents():
    """Retrieve all stored documents."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, filename, page_number, LENGTH(content) as size FROM documents")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_chunks():
    """Retrieve all stored chunks."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, document_id, chunk_index, chunk_size FROM chunks")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_document_text():
    """Retrieve all document text concatenated."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT content FROM documents ORDER BY filename, page_number")
    rows = cur.fetchall()
    conn.close()
    return "\n".join(row[0] for row in rows if row[0])
