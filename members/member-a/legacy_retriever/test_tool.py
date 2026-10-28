from tool_literature import literature_retrieve

if __name__ == "__main__":
    print("==== 测试 literature_retrieve 工具 ====")
    resp = literature_retrieve.invoke({"query": "电解槽停机后反向电流是怎么产生的？"})
    print(resp)
