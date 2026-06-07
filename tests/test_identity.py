import asyncio
from pathlib import Path

from omega_agent.codex_backend import build_codex_prompt
from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent import OmegaRuntime
from omega_agent.runtime.system_prompt import build_system_prompt


def test_system_prompt_omega_identity_hides_provider_by_default(tmp_path: Path):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, provider="codex", default_model_ref="codex/gpt-5.5")

    prompt = build_system_prompt(cfg, tools=[], skills=[], memories=[], settings={"provider": "codex", "model": "gpt-5.5", "host": "127.0.0.1"})

    assert "Tu es Omega Agent" in prompt
    assert "Le fournisseur de modèle est un détail technique interne" in prompt
    assert "Provider: codex" not in prompt
    assert "Modele: gpt-5.5" not in prompt


def test_codex_provider_prompt_does_not_inject_codex_identity():
    prompt = build_codex_prompt([], "Présente-toi")

    forbidden = ["via Codex", "depuis Codex", "wrapper", "backend"]
    for fragment in forbidden:
        assert fragment.lower() not in prompt.lower()


def test_present_yourself_response_uses_omega_identity(tmp_path: Path):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, provider="codex", default_model_ref="codex/gpt-5.5")
    runtime = OmegaRuntime(cfg)

    output = asyncio.run(runtime.send_message("Présente-toi"))

    assert "Omega Agent" in output
    forbidden = ["Codex", "depuis Codex", "wrapper", "backend"]
    for fragment in forbidden:
        assert fragment.lower() not in output.lower()


def test_current_model_question_can_include_selected_model(tmp_path: Path):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, provider="codex", default_model_ref="codex/gpt-5.5")
    runtime = OmegaRuntime(cfg)

    output = asyncio.run(runtime.send_message("Quel modèle utilises-tu ?"))

    assert "codex/gpt-5.5" in output
