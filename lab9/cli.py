import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import sys
import os
import uuid
import torch
from PyPDF2 import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFacePipeline
from langchain_community.vectorstores import FAISS
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain_classic.memory import ConversationBufferMemory
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv
from db import (
    init_db, store_document_pages, store_chunks, store_chat_message,
    get_document_text, get_all_documents, get_all_chunks,
)


def extract_pdf_text(pdf_paths):
    all_text = ""
    for path in pdf_paths:
        if not os.path.exists(path):
            print(f"Warning: File not found: {path}")
            continue
        print(f"Extracting text from: {path}")
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            pages.append(page_text)
            all_text += page_text
        store_document_pages(os.path.basename(path), pages)
        print(f"  -> {len(pages)} pages extracted")
    return all_text


def create_chunks(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        length_function=len,
    )
    chunks = splitter.split_text(text)
    store_chunks(chunks)
    print(f"Created {len(chunks)} text chunks")
    return chunks


def create_vectorstore(chunks):
    print("Creating embeddings and vector store...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    vectorstore = FAISS.from_texts(texts=chunks, embedding=embeddings)
    print("Vector store created")
    return vectorstore


def create_conversation_chain(vectorstore):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    print(f"Loading LLM: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.float16 if device == "cuda" else torch.float32
    ).to(device)
    tokenizer.pad_token = tokenizer.eos_token
    model.generation_config.max_new_tokens = 512
    model.generation_config.max_length = None
    pipe = pipeline("text-generation", model=model, tokenizer=tokenizer,
                    device=model.device, return_full_text=False)
    llm = HuggingFacePipeline(pipeline=pipe)

    custom_prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            "Based on the following context, answer the question concisely.\n\n"
            "Context:\n{context}\n\n"
            "Question: {question}\n\n"
            "Answer:"
        ),
    )

    memory = ConversationBufferMemory(
        memory_key="chat_history", return_messages=True
    )
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vectorstore.as_retriever(
            search_type="similarity", search_kwargs={"k": 4}
        ),
        memory=memory,
        combine_docs_chain_kwargs={"prompt": custom_prompt},
    )
    print("Conversation chain ready\n")
    return chain


def main():
    load_dotenv()
    init_db()

    pdf_paths = sys.argv[1:]

    # Step 1: Extract text
    if pdf_paths:
        print("=" * 50)
        print("Step 1: PDF Text Extraction")
        print("=" * 50)
        raw_text = extract_pdf_text(pdf_paths)
    else:
        print("No PDF paths provided. Checking database for existing documents...")
        docs = get_all_documents()
        if not docs:
            print("Error: No documents in database. Provide PDF paths as arguments.")
            print("Usage: python cli.py <pdf_path> [<pdf_path2> ...]")
            sys.exit(1)
        print(f"Found {len(docs)} pages in database")
        raw_text = get_document_text()

    if not raw_text.strip():
        print("Error: No text extracted from documents.")
        sys.exit(1)

    # Step 2: Create chunks
    print("\n" + "=" * 50)
    print("Step 2: Text Chunking")
    print("=" * 50)
    chunks = create_chunks(raw_text)

    # Step 3: Create vector store
    print("\n" + "=" * 50)
    print("Step 3: Vector Store Creation")
    print("=" * 50)
    vectorstore = create_vectorstore(chunks)

    # Step 4: Create conversation chain
    print("\n" + "=" * 50)
    print("Step 4: Loading LLM & Conversation Chain")
    print("=" * 50)
    chain = create_conversation_chain(vectorstore)

    # Step 5: Interactive Q&A loop
    session_id = str(uuid.uuid4())
    print("=" * 50)
    print("PDF Q&A Chatbot Ready!")
    print("Type your question and press Enter.")
    print("Type 'exit' to quit.")
    print("=" * 50)

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() == "exit":
            print("Goodbye!")
            break

        store_chat_message(session_id, "user", question)
        response = chain({"question": question})
        answer = response["answer"]
        store_chat_message(session_id, "assistant", answer)
        print(f"\nBot: {answer}")


if __name__ == "__main__":
    main()
