from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.tools.memory import _recall, _remember, init_db, memory_db_path


def test_memory_db_is_created_in_workspace_dot_omega(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    init_db(cfg)

    db_path = Path(memory_db_path(cfg))
    assert db_path == tmp_path / ".omega" / "memory.db"
    assert db_path.exists()


def test_remember_and_recall_use_workspace_memory(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)

    assert _remember(cfg, "Je préfère des réponses concises.", "preferences") == "Mémoire enregistrée."
    result = _recall(cfg, "concises")

    assert "réponses concises" in result
    assert "[preferences]" in result
    assert (tmp_path / ".omega" / "actions.jsonl").exists()
