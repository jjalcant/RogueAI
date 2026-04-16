import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader

PROJECTS = r"C:\RogueAI\projects"
DB = r"C:\RogueAI\memory\db"

emb = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100
)

def load_project(path):
    docs = []

    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith((".py",".js",".ts",".md",".txt",".json",".yaml",".yml")):
                p = os.path.join(root,file)
                try:
                    loader = TextLoader(p, encoding="utf-8")
                    docs.extend(loader.load())
                except:
                    pass

    return docs

project = input("Project folder name: ")

path = os.path.join(PROJECTS, project)

docs = load_project(path)

chunks = splitter.split_documents(docs)

db = Chroma(
    persist_directory=DB,
    embedding_function=emb
)

db.add_documents(chunks)

print(f"Indexed {len(chunks)} chunks from project")