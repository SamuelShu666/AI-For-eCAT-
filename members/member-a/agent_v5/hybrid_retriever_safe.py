import os
import re

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from sklearn.feature_extraction.text import TfidfVectorizer

PERSIST_DIR = "./chroma_her_db_v5"

ELEMENTS = ["Ni", "Mo", "Co", "Fe", "W", "Pt", "Ru", "Rh",
            "Pd", "Ag", "Cu", "Sn", "Al", "Cr", "Mn", "Mg",
            "Ir", "Au", "Zn"]

embeddings = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",
    cache_folder="./model_cache",
    encode_kwargs={"normalize_embeddings": True},
)
vectorstore = Chroma(persist_directory=PERSIST_DIR, embedding_function=embeddings)
vector_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

all_docs = vectorstore.get()
doc_texts = all_docs["documents"]
doc_metas = all_docs["metadatas"]

tfidf = TfidfVectorizer(stop_words="english")
tfidf_matrix = tfidf.fit_transform(doc_texts)


def expand_query(query: str) -> str:
    """把 Ni Mo 这类写法补成 NiMo / Ni-Mo，和论文里的写法对齐"""
    found = [e for e in ELEMENTS if re.search(rf"\b{e}\b", query)]
    aliases = []
    for i in range(len(found)):
        for j in range(i + 1, len(found)):
            a, b = found[i], found[j]
            aliases.append(a + b)
            aliases.append(f"{a}-{b}")
    if not aliases:
        return query
    return query + " " + " ".join(aliases)


def tfidf_retrieve(query: str, top_n=5):
    q_vec = tfidf.transform([query])
    scores = (tfidf_matrix * q_vec.T).toarray()[:, 0]
    res = []
    for i in scores.argsort()[::-1]:
        if scores[i] <= 0:
            continue
        res.append({
            "text": doc_texts[i],
            "metadata": doc_metas[i],
            "source": "tfidf",
            "rank": None,
        })
        if len(res) >= top_n:
            break
    return res


def rrf_merge(vec_list, tfidf_list, k=60):
    rank_dict = {}
    for source_name, items in (("vector", vec_list), ("tfidf", tfidf_list)):
        for rank, item in enumerate(items, start=1):
            key = item["metadata"].get("chunk_id") or item["text"][:80]
            score = 1.0 / (k + rank)
            if key in rank_dict:
                rank_dict[key]["score"] += score
                rank_dict[key]["item"]["source"] += "+" + source_name
            else:
                item = dict(item)
                item["source"] = source_name
                rank_dict[key] = {"item": item, "score": score}
    return [v["item"] for v in
            sorted(rank_dict.values(), key=lambda x: x["score"], reverse=True)]


def hybrid_search(query: str, top_k=4):
    q = expand_query(query)
    vec_raw = vector_retriever.invoke(q)
    vec_list = [{"text": d.page_content, "metadata": d.metadata, "source": "vector"}
                for d in vec_raw]
    tfidf_list = tfidf_retrieve(q, top_n=5)
    return rrf_merge(vec_list, tfidf_list)[:top_k]


if __name__ == "__main__":
    while True:
        q = input("\n混合检索提问（exit 退出）：")
        if q.strip().lower() == "exit":
            break
        print("  扩展后:", expand_query(q))
        for idx, item in enumerate(hybrid_search(q, top_k=4), start=1):
            m = item["metadata"]
            print(f"\n[{idx}] 来源={item['source']} chunk={m.get('chunk_id')}")
            print(f"    文献={m.get('paper_title', '')[:50]}")
            print(f"    页码=p{m.get('page_start')}-{m.get('page_end')}")
            print(f"    片段={item['text'][:200]}")