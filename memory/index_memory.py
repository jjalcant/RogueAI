import os
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from sentence_transformers import SentenceTransformer
from langchain_community.embeddings import HuggingFaceEmbeddings

BASE = r"C:\RogueAI\memory"
DOCS = os.path.join(BASE, "knowledge")
DB   = os.path.join(BASE, "db")

emb = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

docs = []
for root, _, files in os.walk(DOCS):
    for f in files:
        p = os.path.join(root, f)
        if f.lower().endswith(".pdf"):
            docs += PyPDFLoader(p).load()
        elif f.lower().endswith((".txt", ".md", ".py", ".js", ".json")):
            docs += TextLoader(p, encoding="utf-8").load()

splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
chunks = splitter.split_documents(docs)

db = Chroma.from_documents(chunks, emb, persist_directory=DB)
db.persist()

print(f"Indexed {len(chunks)} chunks into {DB}")