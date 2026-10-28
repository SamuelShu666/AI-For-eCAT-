from langchain_core.tools import tool
from hybrid_retriever_safe import hybrid_search

@tool
def literature_retrieve(query: str) -> str:
    """
    HER反向电流文献知识库检索工具
    使用场景：需要查阅论文原文、机理解释、实验现象、防护方案、文献证据时调用
    规则：第一轮Agent思考优先调用本工具；后续轮次可和图谱查询一起使用
    Args:
        query: str: 面向文献检索的自然语言问题
    Returns:
        拼接好的带溯源信息的文献片段文本，包含来源、PDF文件名、chunk_id
    """
    res_list = hybrid_search(query, top_k=4)
    blocks = []
    for idx, item in enumerate(res_list):
        meta = item["metadata"]
        block = (
            f"【文献片段 {idx+1}】\n"
            f"召回来源: {item['source']}\n"
            f"原始文档: {meta.get('source_file')}\n"
            f"chunk_id: {meta.get('chunk_id')}\n"
            f"page_number: {meta.get('page_number') or '未记录'}\n"
            f"正文：{item['text']}"
        )
        blocks.append(block)
    return "\n\n".join(blocks)
