# Prompts Codex pour construire Omega Agent

## Prompt 1 — Bootstrap sécurisé

Tu es Codex. Travaille dans ce dépôt uniquement. Crée ou améliore Omega Agent, un agent IA personnel local-first en Python.

Objectifs v0.1 :
- Agent nommé "Omega Agent".
- CLI interactive `omega`.
- Accès fichiers limité à `OMEGA_WORKSPACE`, par défaut `~/omega_workspace`.
- Outils : `list_files`, `read_file`, `write_file`, `run_shell`, `remember`, `recall`.
- Shell sans `sudo`, sans accès hors workspace, allowlist de commandes.
- Confirmation utilisateur avant écriture fichier et shell.
- Logs JSONL dans `.omega/actions.jsonl`.
- Tests pytest pour path traversal, commandes interdites et mémoire.

Contraintes sécurité :
- Ne jamais donner accès à tout le HOME.
- Ne jamais ajouter sudo.
- Ne jamais lire `.ssh`, `.env`, keychain, navigateur ou tokens sauf demande explicite et confirmation.
- Toute action destructive doit nécessiter une confirmation.

Quand tu modifies le code, lance `pytest`. Si un test échoue, corrige avant de terminer.

## Prompt 2 — UX développeur

Améliore la CLI de Omega Agent :
- Ajoute commandes `/help`, `/workspace`, `/model`, `/exit`.
- Affiche les actions outillées de manière lisible.
- Préserve l'historique conversationnel dans une session.
- Ajoute un mode `--no-approval` uniquement pour les tests, jamais par défaut.

## Prompt 3 — Mémoire utile

Améliore la mémoire :
- Table SQLite `memories(id, content, tags, created_at)`.
- Outil `remember(content, tags)`.
- Outil `recall(query)` avec recherche LIKE simple.
- Commande CLI `/memory` pour afficher les dernières entrées.

## Prompt 4 — Navigateur plus tard

Ajoute un module navigateur seulement après v0.1 :
- Playwright optionnel.
- Accès web désactivé par défaut.
- Confirmation avant formulaire, login, achat, publication ou message.

## Prompt 5 — Omega Gateway et Omega Control

Transforme Omega Agent en plateforme locale avec:
- Gateway FastAPI.
- Omega Control en Vite React TypeScript Tailwind.
- Sessions SQLite avec messages user, assistant, system, tool.
- REST + WebSocket avec événements typés.
- Registries tools, skills, plugins.
- Approvals persistantes pour actions sensibles.
- Provider Codex OAuth conservé.
- Sandbox `OMEGA_WORKSPACE` conservé.

Contraintes:
- Ne pas copier OpenClaw, sa marque, son logo ou ses assets.
- Produit: Omega Agent.
- Interface: Omega Control.
- Bind par défaut: `127.0.0.1:8765`.
- Ne jamais lire `~/.codex/auth.json`.
- Ne jamais exécuter de code plugin externe en v0.1.
- Lancer `pytest` après modification.
