"""
agent_loader.py  (repo root)
Helper that resolves Python path issues when importing the AI agent
from orchestrator.py which lives in 03_Governance/.
"""
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _05_Agent.aura_agent import run_aura_agent  # noqa: F401


def start_agent_daemon():
    """Start the AURA AI Agent in daemon thread mode."""
    return run_aura_agent(mode="daemon")
