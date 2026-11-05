"""对话写入知识库资料。运行时按 langchain:wiki_material 加载。"""

from apps.opspilot.metis.llm.tools.wiki_material.save import save_wiki_material

__all__ = ["save_wiki_material"]
