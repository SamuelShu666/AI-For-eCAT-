from langchain_core.tools import tool

from hybrid_retriever_safe import hybrid_search

PAPER_TITLES = {
    "P01": "Effects of operation and shutdown parameters and electrode materials on the reverse current phenomenon in alkaline water analyzers (J. Power Sources, 2022)",
    "P02": "Dependence of the reverse current on the surface of electrode placed on a bipolar plate in an alkaline water electrolyzer (Electrochemistry, 2018)",
    "P03": "Reverse-Current Tolerance for Hydrogen Evolution Reaction Activity of Lead-Decorated Nickel Catalysts (Adv. Funct. Mater., 2024)",
    "P04": "Probing Electrode Transformation under Dynamic Operation for Alkaline Water Electrolysis (Adv. Energy Mater., 2025)",
    "P05": "Reverse-Current Induced Cascade Degradation in Ni-Ru Electrodes (Adv. Energy Mater., 2025)",
    "P06": "Cathodic Protection System against a Reverse Current after Shut-Down in Zero-Gap Alkaline Water Electrolysis (JACS Au, 2022)",
    "P07": "Relationship between the Redox Reactions on a Bipolar Plate and Reverse Current after Alkaline Water Electrolysis (Electrocatalysis, 2018)",
    "P08": "Strategies and Countermeasures against Reverse Current for Enhanced Durability in Water Electrolysis Systems (Small Methods, 2025)",
    "P09": "Superior hydrogen production and long-term stability of NiSn alloy protected by carbon-shell in alkaline water electrolysis (Appl. Surf. Sci., 2025)",
    "P10": "Structural evolution of amorphous CoMo alloy in alkaline based hydrogen evolution reaction (Appl. Surf. Sci., 2025)",
    "P11": "Revealing the role of Sn in NiSn for enhancing hydrogen evolution performance by density functional theory (Int. J. Hydrogen Energy, 2023)",
    "P12": "Enhanced hydrogen adsorption-desorption reversibility found on NiAl alloy: A first-principles study (Int. J. Hydrogen Energy, 2024)",
    "P13": "Structural and compositional optimization of bimetallic NiCo alloy nanoparticles for promotion of alkaline hydrogen evolution reaction (J. Power Sources, 2025)",
    "P14": "NiRh nanosponges with highly efficient electrocatalytic performance for hydrogen evolution reaction (J. Alloys Compd., 2019)",
    "P15": "Hierarchical NiMo-based 3D electrocatalysts for highly-efficient hydrogen evolution in alkaline conditions (Nano Energy, 2016)",
    "P16": "NiMo Solid Solution Nanowire Array Electrodes for Highly Efficient Hydrogen Evolution Reaction (Adv. Funct. Mater., 2019)",
    "P17": "Dual Active Site Engineering in Porous NiW Bimetallic Alloys for Enhanced Alkaline Hydrogen Evolution Reaction (Adv. Mater., 2025)",
    "P18": "Electrocatalysts for Hydrogen Evolution in Alkaline Electrolytes: Mechanisms, Challenges, and Prospective Solutions (Adv. Sci., 2017)",
    "P19": "Ultrathin NiPt Single-Atom Alloy for Synergistically Accelerating Alkaline Hydrogen Evolution (ACS Appl. Energy Mater., 2022)",
    "P20": "Regulating Hollow Carbon Cage Supported NiCo Alloy Nanoparticles for Efficient Electrocatalytic Hydrogen Evolution Reaction (ACS Appl. Mater. Interfaces, 2023)",
    "P21": "Interfacial Hydrogen Spillover in Partially Alloyed PdNi Electrocatalysts for Hydrogen Evolution (Angew. Chem. Int. Ed., 2026)",
    "P22": "Low-ruthenium-content NiRu nanoalloys as highly efficient and pH-universal electrocatalysts for the hydrogen evolution reaction (J. Mater. Chem. A, 2017)",
    "P23": "AgNi Alloy Nanoparticles as Dual-Function Catalysts for Sustainable Nitrile Hydration and Electrocatalytic Hydrogen Generation (ChemCatChem, 2025)",
    "P24": "RuO2/NiRu Heterogeneous Interface Optimizes the d-Band Center for High-Performance Alkaline Hydrogen Evolution (J. Mater. Chem. A, 2023)",
    "P25": "Boosting the HER/OER bifunctional electrocatalytic activity of Ni-Cu alloy via water-containing deep eutectic solvent (J. Mater. Chem. A, 2025)",
    "P26": "Tungsten-Nickel Alloy Boosts Alkaline Hydrogen Evolution Reaction (J. Phys. Chem. C, 2021)",
    "P27": "Mixture Design of NiCoMo Ternary Alloy Nanoparticles Decorated with Ru: A Pt/C-like Activity for Hydrogen Evolution (J. Phys. Chem. C, 2018)",
    "P28": "Ternary alloy nanocatalysts for hydrogen evolution reaction (Bull. Mater. Sci., 2016)",
    "P29": "Three-Phase Heterojunction NiMo-Based Nano-Needle for Water Splitting at Industrial Alkaline Condition (Nano-Micro Lett., 2021)",
    "P30": "Yttrium-doped NiMo-MoO2 heterostructure electrocatalysts for hydrogen production from alkaline seawater (Nat. Commun., 2025)",
    "P31": "Electronic Structure Modulation of Palladium by Nickel Doping for Highly Efficient Hydrogen Evolution in Acidic Media (ACS Sustain. Chem. Eng., 2025)",
}


@tool
def literature_retrieve(query: str) -> str:
    """
    HER 与抗反向电流文献知识库检索工具。

    使用场景：需要论文原文、机理解释、成分选择依据、防护方案、文献证据时调用。
    重要：知识库正文是英文，query 必须写成英文检索式。
    中文问题请先翻译成英文关键词再调用。

    Args:
        query: 英文检索式，例如 "Ni Mo alloy hydrogen evolution alkaline"

    Returns:
        4 条带溯源的文献片段：论文标题、paper_id、页码、chunk_id、召回来源、正文
    """
    results = hybrid_search(query, top_k=4)
    if not results:
        return "未检索到相关文献片段。"

    blocks = []
    for i, item in enumerate(results, start=1):
        m = item.get("metadata", {})
        pid = m.get("paper_id", "")
        title = PAPER_TITLES.get(pid, m.get("paper_title", "未知论文"))

        p0, p1 = m.get("page_start", ""), m.get("page_end", "")
        if not p0:
            page = "页码未知"
        elif str(p0) == str(p1):
            page = f"p{p0}"
        else:
            page = f"p{p0}-{p1}"

        blocks.append(
            f"【文献片段 {i}】\n"
            f"论文: {title}\n"
            f"paper_id: {pid}\n"
            f"页码: {page}\n"
            f"chunk_id: {m.get('chunk_id', '未知')}\n"
            f"召回来源: {item.get('source', '')}\n"
            f"正文: {item.get('text', '')}"
        )

    return "\n\n".join(blocks)