from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from sklearn.feature_extraction.text import TfidfVectorizer
import os

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
PERSIST_DIR = "./chroma_her_db"

embeddings = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",
    cache_folder="./model_cache",
    encode_kwargs={"normalize_embeddings": True}
)
vectorstore = Chroma(persist_directory=PERSIST_DIR, embedding_function=embeddings)
vector_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

all_docs = vectorstore.get()
doc_texts = all_docs["documents"]
doc_metas = all_docs["metadatas"]

tfidf = TfidfVectorizer(stop_words="english")
tfidf_matrix = tfidf.fit_transform(doc_texts)

def tfidf_retrieve(query: str, top_n=5):
    q_vec = tfidf.transform([query])
    scores = (tfidf_matrix * q_vec.T).toarray()[:,0]
    idx_sorted = scores.argsort()[::-1][:top_n]
    res = []
    for i in idx_sorted:
        res.append({
            "text": doc_texts[i],
            "metadata": doc_metas[i],
            "source": "tfidf",
            "rank": None
        })
    return res

def rrf_merge(vec_list, tfidf_list, k=60):
    """RRF 倒数排名融合"""
    rank_dict = {}
    for rank, item in enumerate(vec_list, start=1):
        key = item["text"].strip()
        score = 1.0 / (k + rank)
        if key in rank_dict:
            rank_dict[key]["score"] += score
        else:
            rank_dict[key] = {"item": item, "score": score}
    for rank, item in enumerate(tfidf_list, start=1):
        key = item["text"].strip()
        score = 1.0 / (k + rank)
        if key in rank_dict:
            rank_dict[key]["score"] += score
        else:
            rank_dict[key] = {"item": item, "score": score}
    sorted_items = sorted(rank_dict.values(), key=lambda x: x["score"], reverse=True)
    return [v["item"] for v in sorted_items]

def hybrid_search(query: str, top_k=4):
    vec_raw = vector_retriever.invoke(query)
    vec_list = [{"text": d.page_content, "metadata": d.metadata, "source": "vector"} for d in vec_raw]
    tfidf_list = tfidf_retrieve(query, top_n=5)
    fused = rrf_merge(vec_list, tfidf_list)
    return fused[:top_k]

if __name__ == "__main__":
    while True:
        q = input("\n🔍RRF混合检索提问（exit退出）：")
        if q.strip().lower() == "exit":
            break
        result = hybrid_search(q, top_k=4)
        print("\n==== RRF融合召回结果 ====")
        for idx, item in enumerate(result):
            meta = item["metadata"]
            print(f"\n[{idx+1}] 来源：{item['source']}")
            print(f"paper_title：{meta.get('paper_title','未记录标题')}")
            print(f"source_file：{meta.get('source_file','未知')}")
            print(f"chunk_id：{meta.get('chunk_id','未知')}")
            print(f"page_number：{meta.get('page_number','')}")
            print(f"片段：{item['text'][:450]}...")
