import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("WINTHOR_MCP_CONFIG", str(RAIZ / "config.exemplo.toml"))
os.environ["WINTHOR_MCP_MODO"] = "exemplo"
