from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

DB = r"C:\RogueAI\memory\db"

emb = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

db = Chroma(
    persist_directory=DB,
    embedding_function=emb
)

while True:
    q = input("\nAsk memory >> ")
    docs = db.similarity_search(q, k=3)

    for d in docs:
        print("\n---")
        print(d.page_content)