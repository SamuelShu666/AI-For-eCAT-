# 文献 PDF 下载包

本目录对应项目整理的 20 篇文献清单。现已下载 **12 篇可直接打开的 PDF**，逐篇状态见 `literature_download_index.csv`。未下载条目保留了 DOI、原始入口及失败原因；拒绝访问或未公开的文件没有用非授权镜像替代。

PDF 均通过 `%PDF-` 文件头检查，并用 Poppler `pdfinfo` 检查到有效页数。当前运行环境未安装 `pdftotext`，因此本次没有对每个文件单独做文本层抽取校验。已下载来源以公开机构仓储、开放期刊或 arXiv 为主。

建议后续使用场景：在用于 3D 文献星云和页码抽屉前，再按 `literature_download_index.csv` 将各 PDF 的文本可选中状态及版权条款核验入库。
