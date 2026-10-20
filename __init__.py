"""ComfyUI Krea 2 Turbo Prompt Builder v0.1.9"""
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ("NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY")

# Optional frontend: basic/advanced/diagnostics widget folding. Core inference works without JS.
WEB_DIRECTORY = "./web"
