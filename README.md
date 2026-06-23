# Omega Agent

Omega Agent est un agent IA local-first conçu pour travailler dans un workspace contrôlé. Il associe une interface web, un Gateway local, un runtime durable, des outils fichiers et shell, une mémoire projet, des policies, des workflows et des mécanismes de snapshot et rollback.

Le projet cible d’abord Windows et PowerShell. Le Gateway écoute par défaut sur `127.0.0.1:8765`, les données opérationnelles restent locales et les outils sont limités au workspace configuré.

## À quoi sert Omega Agent

Omega Agent permet de :

- piloter un workspace local depuis Omega Control ou la CLI ;
- lire, créer et modifier des fichiers autorisés ;
- analyser la structure et l’état d’un projet ;
- exécuter des commandes contrôlées dans le workspace ;
- conserver chaque demande sous forme de run durable ;
- suivre les étapes, actions, décisions de policy et événements ;
- appliquer des règles de sécurité, de risque et de budget ;
- créer des snapshots avant les mutations prises en charge par le runtime ;
- restaurer un fichier ou un run avec le rollback ;
- conserver une mémoire structurée par projet, session ou run ;
- définir et exécuter des workflows ;
- configurer et sélectionner des providers et modèles selon les capacités disponibles.

## Ce qu’Omega Agent n’est pas

- Ce n’est pas un simple wrapper Codex. Omega Agent possède son propre Gateway, son runtime, ses tools, ses policies, sa mémoire, ses workflows et son interface.
- Ce n’est pas un agent sans contrôle de sécurité. Les outils passent par des validations de chemin, de risque, de policy et, selon la configuration, d’approval.
- Ce n’est pas un outil conçu pour écrire partout sur la machine. La frontière principale reste le workspace.
- Ce n’est pas un service cloud obligatoire. Le Gateway, Omega Control et la base SQLite fonctionnent localement.
- Ce n’est pas une garantie d’autonomie illimitée. Les actions externes, sensibles ou expérimentales restent désactivées, refusées ou soumises à validation selon leur configuration.

## Fonctionnalités principales

### Omega Control

Interface React locale pour le chat, les runs, les snapshots, les policies, les modèles, la mémoire, les workflows, les connecteurs, les évaluations et les diagnostics.

### Local Gateway

Serveur FastAPI local qui expose l’API, le WebSocket et les fichiers statiques d’Omega Control. Le bind par défaut reste `127.0.0.1:8765`.

### Workspace Tools

Outils pour lire, écrire, ajouter, copier, déplacer et supprimer des fichiers, lister le workspace, exécuter un shell contrôlé et utiliser des commandes Git locales autorisées.

### Durable Runtime

Chaque action passe par un run persistant composé de steps, checkpoints, actions journalisées, observations et statuts de reprise.

### Snapshots et rollback

Le runtime peut capturer l’état d’un fichier avant modification ou suppression, restaurer un fichier existant et supprimer un fichier créé lors d’un rollback.

### Policy Studio et sécurité

Profils, règles personnalisées, simulation de policy, classification des actions, approvals et refus strict des actions `system_sensitive`.

### Budget et Risk Governor

Limites sur les actions, les appels de tools, le shell, les fichiers modifiés, les suppressions, les appels externes et le niveau de risque maximal.

### Model Providers

Registre de providers, catalogue de modèles, statut d’authentification, préférences globales, projet et session, ainsi que sélection de modèle au runtime. Les capacités d’exécution dépendent de l’adapter actif ; voir [Providers IA](#providers-ia).

### Project Memory

Mémoire SQLite avec scopes, provenance, confiance, importance, tags, décisions et suggestions. Les données sensibles sont filtrées avant stockage ou affichage.

### Workflows

Définitions validées, templates, runs de workflow, pause, reprise, annulation, retry d’étape et exécution shadow lorsque la configuration le demande.

### Code Workspace Agent

Profil spécialisé pour scanner un dépôt, détecter sa stack, lancer des tests, produire un diff, préparer un plan de patch et créer un commit local si la policy l’autorise.

### Evals et traces

Datasets d’évaluation, scoring de runs, métriques, traces exportables et redacted, rapports et regroupement des échecs.

### Connectors et capabilities

Registres pour connecteurs locaux, GitHub, OpenAPI, MCP et A2A. Les sources non fiables sont désactivées par défaut et les capacités MCP/A2A d’exécution sont désactivées par défaut.

### Skills

Skills locales, versions, tests statiques, activation explicite et Skill Foundry pour proposer des candidates à partir de runs réussis.

### Research et graphe de preuves

Runs de recherche locale, sources, claims, preuves, confiance et export Markdown ou JSON. Le web reste désactivé tant qu’un connecteur adapté n’est pas configuré.

### Flux temps réel

Le WebSocket diffuse les statuts et événements redacted vers Omega Control. Le protocole persistant permet aussi le replay à partir d’un identifiant d’événement.

### Shadow Execution

Exécution isolée sous `.omega/shadow/<id>/workspace`, calcul d’un diff prévisionnel et promotion explicite vers le workspace réel. Les effets externes non isolables peuvent être marqués comme non simulables.

### Automatisation navigateur et bureau

Les outils Playwright et desktop sont optionnels, expérimentaux et désactivés par défaut. Les actions visibles ou sensibles conservent leurs validations et approvals.

> **Note :** ces surfaces peuvent changer et ne doivent pas être considérées comme stables.

## Architecture

```text
Utilisateur
   |
   +--> Omega Control
   |        |
   +--> CLI omega
            |
            v
      Omega Gateway
      FastAPI + WebSocket
            |
            v
       Omega Runtime
       |     |      |
       |     |      +--> Providers de modèles
       |     |
       |     +--> Policies + Risk/Budget Governor
       |
       +--> Tools + Workflows + Connectors
                    |
                    v
              Workspace contrôlé

       Runtime + Gateway --> SQLite locale
```

Principaux répertoires :

| Chemin | Rôle |
|---|---|
| `omega_agent/gateway/` | Gateway FastAPI, routes REST, WebSocket et service des assets |
| `omega_agent/runtime/` | Runs, sessions, tools registry, approvals, snapshots, événements et orchestration |
| `omega_agent/security/` | Sandbox, résolution des chemins, policies, risque, redaction et audit |
| `omega_agent/providers/` | Registre et adapters de providers |
| `omega_agent/tools/` | Implémentations fichiers, shell, Git, navigateur et bureau |
| `omega_agent/workflows/` | Validation, stockage, templates et exécution des workflows |
| `omega_agent/evals/` | Scoring, métriques, traces et rapports |
| `omega_agent/connectors/` | Registre, opérations et import OpenAPI |
| `omega_agent/shadow/` | Plans shadow, exécution isolée, diff et promotion |
| `omega_control/` | Interface React/Vite |
| `tests/` | Tests unitaires, d’intégration et CLI |
| `$HOME\.omega\config.json` | Configuration utilisateur principale |
| `$HOME\.omega\omega.db` | Base SQLite par défaut |
| `workspace.path` | Racine des fichiers et commandes contrôlés |

## Installation

### Prérequis

- Windows avec PowerShell ;
- Python 3.11 ou supérieur ;
- Git ;
- Node.js et npm pour reconstruire Omega Control.

### Installation développeur

Ce parcours constitue le démarrage rapide recommandé pour travailler sur le dépôt.

```powershell
git clone https://github.com/OmegaMc1331/Omega-Agent.git
cd Omega-Agent

python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e .
```

Le dépôt contient un build d’Omega Control. Pour le reconstruire :

```powershell
cd omega_control
npm install
npm run build
cd ..
```

Initialisez ensuite la configuration et lancez les diagnostics :

```powershell
omega config init
omega doctor
omega workspace doctor
```

Lancez Omega Agent :

```powershell
omega
```

Cette commande démarre le Gateway s’il n’est pas déjà actif et ouvre Omega Control. Pour démarrer uniquement le serveur :

```powershell
omega serve --no-open
```

### Installation automatisée

Le script Windows installe l’application sous `%LOCALAPPDATA%\OmegaAgent`, crée la venv, prépare la configuration et installe la commande PowerShell :

```powershell
iwr https://raw.githubusercontent.com/OmegaMc1331/Omega-Agent/main/install.ps1 -OutFile install-omega.ps1
powershell -ExecutionPolicy Bypass -File .\install-omega.ps1
```

Lisez le script avant de l’exécuter. L’option `-Force` remplace le répertoire d’installation existant ; elle ne doit être utilisée que pour une réinstallation volontaire.

## Mettre à jour Omega Agent

Une installation Git existante peut être mise à jour sans désinstaller Omega Agent :

```powershell
omega update
```

La commande :

- affiche le commit, la branche et l’état du dépôt ;
- sauvegarde `$HOME\.omega\config.json` avant toute modification ;
- récupère les changements avec Git et refuse les merges non fast-forward ;
- met à jour la venv et l’installation Python éditable ;
- installe les dépendances et reconstruit Omega Control lorsque Node.js est disponible ;
- ajoute les nouvelles clés de configuration sans remplacer les valeurs utilisateur ;
- lance `omega doctor` puis `omega workspace doctor`.

Le workspace, la base runtime, les credentials locaux, les logs et les fichiers personnels ne sont ni supprimés ni réinitialisés.

Options disponibles :

```powershell
# Conserver les changements locaux dans un stash nommé, puis mettre à jour
omega update --force

# Basculer sur main puis effectuer un pull --ff-only depuis origin
omega update --branch main

# Mettre à jour uniquement Git et Python
omega update --skip-frontend

# Ne pas lancer les diagnostics finaux
omega update --skip-doctor
```

Sans `--force`, un dépôt contenant des modifications suivies ou non suivies est refusé et la liste des fichiers concernés est affichée. Avec `--force`, ces modifications sont placées dans un stash Git explicite ; elles ne sont pas supprimées et le stash n’est pas réappliqué automatiquement.

Le script d’installation expose le même chemin pour une installation sous `%LOCALAPPDATA%\OmegaAgent` :

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Update
```

## Configuration

La source de vérité est :

```text
$HOME\.omega\config.json
```

Vous pouvez afficher son chemin et vérifier sa validité :

```powershell
omega config path
omega config doctor
omega config show
```

Clés principales :

| Clé | Rôle |
|---|---|
| `workspace.path` | Dossier racine accessible aux tools |
| `workspace.full_access` | Autorise les actions workspace-safe sans approval systématique |
| `workspace.require_approval` | Active les approvals générales selon les policies |
| `workspace.shell_full_access` | Autorise la surface shell étendue, toujours filtrée |
| `workspace.allow_delete` | Autorise les suppressions dans le workspace |
| `workspace.allow_git_write` | Autorise les opérations Git locales en écriture |
| `codex.sandbox_mode` | Sandbox demandé au backend Codex |
| `codex.approval_policy` | Politique d’approval demandée au backend Codex |
| `providers.default` | Provider sélectionné par défaut |
| `providers.items.*` | Type, activation, URL, référence de secret et modèle manuel des providers |
| `models.default` | Référence du modèle par défaut, au format `provider/model` |
| `models.fallback` | Référence de fallback optionnelle |
| `paths.db_path` | Chemin de la base SQLite |
| `gateway.host` | Adresse d’écoute du Gateway |
| `gateway.port` | Port d’écoute du Gateway |

Exemple minimal :

```json
{
  "workspace": {
    "path": "C:\\Users\\<vous>\\omega_workspace",
    "full_access": true,
    "require_approval": false,
    "shell_full_access": true,
    "allow_delete": true,
    "allow_git_write": true
  },
  "codex": {
    "sandbox_mode": "workspace-write",
    "approval_policy": "never"
  },
  "providers": {
    "default": "codex"
  },
  "models": {
    "default": "codex/gpt-5.5",
    "fallback": null
  },
  "paths": {
    "db_path": "C:\\Users\\<vous>\\.omega\\omega.db"
  }
}
```

`workspace.full_access=true` élargit les actions autorisées à l’intérieur du workspace. Cette option n’autorise pas les chemins extérieurs, les traversals, les symlinks sortants, les fichiers sensibles ou les commandes système dangereuses.

Modifiez la configuration avec la CLI plutôt qu’en éditant le JSON à la main :

```powershell
omega config get workspace.path
omega config set workspace.full_access true
omega config set workspace.require_approval false
omega config set workspace.allow_delete true
omega config set paths.db_path "$HOME\.omega\omega.db"
```

Les références de secrets sont déclarées dans `config.json`, mais leurs valeurs restent dans l’environnement utilisateur ou dans un gestionnaire de secrets externe. Omega ne doit pas écrire les valeurs d’API dans SQLite ou les exposer dans l’interface.

## Commandes CLI

Les commandes suivantes sont enregistrées dans `omega_agent/main.py`.

### Lancement et diagnostics

```powershell
omega
omega serve
omega serve --no-open
omega chat
omega doctor
omega workspace doctor
omega runtime doctor
omega policy doctor
omega budgets doctor
omega code doctor
omega security audit
```

### Workspace et runtime

```powershell
omega tools list
omega tools test write-file
omega tools test shell
omega runs list
omega runs show <run_id>
omega runs resume <run_id>
omega runs cancel <run_id>
omega runs replay <run_id>
omega rollback list
omega rollback snapshot <snapshot_id>
omega rollback run <run_id>
omega events list
omega traces list
```

### Policies et gouvernance

```powershell
omega policy profiles
omega policy rules
omega policy simulate --tool write_file --path test-policy.txt
omega budgets profiles
omega budgets usage
omega budgets violations
omega budgets simulate --tool write_file --risk high --category reversible_write
```

### Modèles, extensions et automatisation

```powershell
omega providers list
omega providers doctor
omega models list
omega models current
omega models status
omega models providers
omega capabilities list
omega connectors list
omega connectors auth-status
omega workflows list
omega workflows templates
omega evals metrics
omega skills list
omega skills candidates
omega plugins list
omega shadow list
omega research list
omega mcp list
omega a2a list
```

### Code et mémoire

```powershell
omega code scan
omega code status
omega code test
omega code diff
omega memory list
omega memory search <query>
omega decisions list
```

Utilisez `omega <commande> --help` pour afficher les arguments exacts d’une commande.

## Utilisation de base

1. Lancez l’application :

   ```powershell
   omega
   ```

2. Dans Omega Control, demandez par exemple :

   ```text
   Crée notes\verification.txt avec le contenu OK.
   ```

3. Vérifiez le fichier dans le workspace, puis consultez le run :

   ```powershell
   omega runs list
   omega runs show <run_id>
   ```

4. Listez les snapshots disponibles :

   ```powershell
   omega rollback list
   ```

5. Si vous devez annuler une mutation, restaurez le snapshot concerné :

   ```powershell
   omega rollback snapshot <snapshot_id>
   ```

Omega Control expose les mêmes informations dans les vues Runs, Timeline et Rollback.

## Sécurité

### Frontière workspace

Les chemins sont normalisés avec `Path.resolve()` puis comparés à la racine résolue du workspace. Les contrôles refusent notamment :

- les chemins hors workspace ;
- les traversals avec `..` ;
- les symlinks qui sortent du workspace ;
- les racines disque et les workspaces trop larges ;
- les chemins sensibles comme `.ssh`, `.env`, cookies, credentials, tokens et clés privées.

### Mutations et rollback

Quand `runtime.snapshots.enabled=true`, les mutations exécutées par le Tool Broker créent un snapshot avant l’action :

- un fichier existant peut être restauré ;
- un fichier créé peut être supprimé par rollback ;
- une suppression autorisée conserve une copie restaurable ;
- un fichier trop volumineux peut être journalisé comme non restaurable selon la limite configurée.

### Policies et approvals

Policy Studio classe les actions en :

- `read_only` ;
- `reversible_write` ;
- `destructive_write` ;
- `external_side_effect` ;
- `system_sensitive`.

Les règles personnalisées peuvent autoriser, refuser ou demander une approval. Budget Governor ne peut qu’ajouter des restrictions ; il n’élargit pas une permission existante.

### Shell

Le shell s’exécute avec le workspace comme `cwd` et un environnement réduit. Les commandes dangereuses, les chemins absolus extérieurs, les traversals, les commandes encodées et les modifications système restent refusés.

### Réseau et exposition

Le Gateway écoute sur loopback par défaut. Un bind LAN doit être explicite et affiche un avertissement. L’accès mobile prévu par le dépôt utilise Tailscale Serve sans activer automatiquement Funnel.

### Redaction

Les actions, événements, traces, métriques et réponses d’API passent par les fonctions de redaction. Les secrets bruts, headers d’autorisation, cookies et fichiers d’authentification ne doivent pas apparaître dans Omega Control ou SQLite.

## Providers et modèles

Omega Agent conserve son identité, ses policies, son runtime et ses tools quel que soit le provider sélectionné. Codex CLI/OAuth est un provider disponible parmi d’autres.

### Afficher et sélectionner un provider

```powershell
omega providers list
omega providers show codex
omega providers use codex
omega providers doctor
```

La configuration réside dans `$HOME\.omega\config.json`. `providers.default` sélectionne le provider et `models.default` sélectionne le modèle global.

### Ajouter un endpoint OpenAI-compatible

Déclarez le nom de la variable d’environnement, jamais sa valeur :

```powershell
omega providers add openrouter `
  --type openai-compatible `
  --base-url https://openrouter.ai/api/v1 `
  --api-key-env OPENROUTER_API_KEY `
  --default-model openai/gpt-oss-120b

omega providers use openrouter
omega models use openrouter/openai/gpt-oss-120b
omega providers test openrouter
```

Définissez ensuite la clé dans l’environnement utilisateur Windows. Omega stocke uniquement `api_key_env` dans `config.json` et masque les headers d’autorisation dans les erreurs et les réponses d’API.

### Utiliser Ollama local

```powershell
omega providers add local-ollama `
  --type ollama `
  --base-url http://localhost:11434 `
  --default-model llama3.1

omega providers use local-ollama
omega models use local-ollama/llama3.1
omega providers test local-ollama
```

Ollama et LM Studio n’exigent pas de clé par défaut. Le service local doit toutefois être démarré pour réussir le test de connexion.

### Gérer les modèles

```powershell
omega models list
omega models list --provider openrouter
omega models refresh --provider openrouter
omega models current
omega models test
omega models test openrouter/openai/gpt-oss-120b
```

La découverte de modèles utilise `/models` pour les endpoints OpenAI-compatible et `/api/tags` pour Ollama. Si la découverte échoue, Omega conserve les modèles configurés manuellement.

### Providers intégrés

Le registre fournit des configurations pour Codex, OpenAI, Anthropic, Google Gemini, Vertex AI, OpenRouter, Groq, Mistral, Ollama, LM Studio, DeepSeek, xAI et les endpoints OpenAI-compatible personnalisés.

Les capacités varient selon le provider et le modèle. Un adapter peut annoncer le chat, le streaming, le tool calling, la vision, le mode JSON ou le reasoning. Quand le tool calling natif n’est pas disponible, Omega conserve son format d’actions structurées interne.

Pour Codex CLI/OAuth, les réglages de sandbox restent distincts :

```powershell
omega config set codex.sandbox_mode workspace-write
omega config set codex.approval_policy never
```

## Développement

### Structure de travail

- Le backend Python se trouve dans `omega_agent/`.
- L’interface React se trouve dans `omega_control/`.
- Les tests se trouvent dans `tests/`.
- Les scripts Windows se trouvent à la racine et dans `scripts/`.
- `AGENTS.md` contient les règles de contribution et de sécurité du dépôt.

### Tests Python

Installez les dépendances de test si nécessaire :

```powershell
python -m pip install pytest httpx
```

Lancez la suite :

```powershell
python -m pytest
```

Sur Windows, utilisez un basetemp extérieur au dépôt si le répertoire temporaire local provoque un `PermissionError` :

```powershell
$base = Join-Path $env:TEMP "omega-agent-pytest-full"
python -m pytest --basetemp "$base"
```

Le dépôt ne doit pas imposer `.pytest-tmp` comme basetemp.

### Build frontend

```powershell
cd omega_control
npm install
npm run build
```

### Conventions minimales

- Limitez toutes les opérations fichiers au workspace.
- N’ajoutez pas d’accès global au système de fichiers.
- Ne stockez pas de secrets dans le dépôt, la base SQLite ou les logs.
- Ajoutez des tests pour chaque changement de policy, de tool ou de runtime.
- Gardez le bind par défaut sur `127.0.0.1`.
- Marquez clairement les surfaces expérimentales et désactivées par défaut.

## Dépannage

### `omega.exe` est introuvable

**Symptôme**

PowerShell ne reconnaît pas la commande `omega`.

**Cause probable**

La venv n’est pas active ou le package n’a pas été installé en mode editable.

**Correction**

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Get-Command omega
```

Pour installer la commande dans le profil PowerShell :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-powershell-command.ps1 -InstallDir (Get-Location) -Force
. $PROFILE
```

### `config.json` est invalide ou contient un BOM

**Symptôme**

`omega config doctor` signale une configuration JSON invalide.

**Cause probable**

Le fichier a été modifié par un éditeur qui a produit du JSON invalide. Le loader actuel accepte un BOM UTF-8, mais certains outils externes peuvent encore mal le traiter.

**Correction**

```powershell
$config = "$HOME\.omega\config.json"
Copy-Item $config "$config.backup"
$data = Get-Content $config -Raw | ConvertFrom-Json
$json = $data | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($config, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
omega config doctor
```

### Le workspace est en lecture seule

**Symptôme**

`omega workspace doctor` échoue au test d’écriture.

**Cause probable**

Le chemin n’existe pas, n’est pas accessible à l’utilisateur Windows ou pointe vers un emplacement protégé.

**Correction**

```powershell
omega config get workspace.path
omega workspace doctor

New-Item -ItemType Directory -Force "$HOME\omega_workspace"
omega config set workspace.path "$HOME\omega_workspace"
omega workspace doctor
```

### Le sandbox Codex reste en lecture seule

**Symptôme**

Le provider indique `filesystem sandbox = read-only` alors que Workspace Full Access est actif.

**Cause probable**

Les clés du backend ne correspondent pas au mode workspace.

**Correction**

```powershell
omega config set workspace.full_access true
omega config set codex.sandbox_mode workspace-write
omega config set codex.approval_policy never
omega doctor
```

Vérifiez aussi que la version installée accepte les options globales :

```powershell
codex --help
codex --version
```

### `write_file` est refusé par la policy

**Symptôme**

Une écriture interne au workspace retourne un refus de policy, de risque, de budget ou de chemin sensible.

**Cause probable**

Le chemin est extérieur ou sensible, une règle personnalisée s’applique, un budget est dépassé ou une approval est requise.

**Diagnostic**

```powershell
omega policy simulate --tool write_file --path test-policy.txt
omega policy doctor
omega budgets doctor
omega workspace doctor
```

Ne contournez pas un refus `outside workspace`, `sensitive path` ou `system_sensitive`. Corrigez le chemin ou la règle concernée.

### Le port Gateway est déjà utilisé

**Symptôme**

Omega signale que le port `8765` appartient à un autre processus.

**Diagnostic**

```powershell
$connection = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
$connection
Get-Process -Id $connection.OwningProcess
```

Si le processus n’est pas Omega et si vous avez vérifié qu’il peut être arrêté :

```powershell
Stop-Process -Id $connection.OwningProcess
```

Vous pouvez aussi sélectionner un autre port :

```powershell
omega config set gateway.port 8766
omega doctor
```

### Pytest échoue avec `PermissionError` sur `.pytest-tmp`

**Symptôme**

Pytest échoue avant ou pendant la collecte avec `WinError 5`.

**Cause probable**

Un ancien dossier temporaire du dépôt est verrouillé ou un script local force encore `--basetemp=.pytest-tmp`.

**Correction**

```powershell
$base = Join-Path $env:TEMP "omega-agent-pytest-full"
python -m pytest --basetemp "$base"
```

Vérifiez aussi qu’aucun alias ou script externe n’ajoute `--basetemp=.pytest-tmp`.

### `npm run build` échoue

**Symptôme**

TypeScript, Vite ou Windows signale une dépendance manquante ou un fichier verrouillé.

**Correction**

```powershell
cd omega_control
npm install
npm run build
```

Si Windows signale un verrou, fermez les processus `npm run dev` ou Vite qui utilisent ce dépôt, puis relancez le build. Utilisez `Get-Process node` pour identifier les processus Node avant toute interruption.

## Roadmap

### Présent et testé

- Gateway local et Omega Control ;
- workspace tools et shell contrôlé ;
- runtime durable, runs, checkpoints et action journal ;
- snapshots et rollback ;
- policies, approvals et Budget/Risk Governor ;
- mémoire projet et décisions ;
- workflows, évaluations, traces et événements ;
- connecteurs, capabilities, skills et shadow execution.

### En cours

La branche actuelle correspond à la version `0.1.0`. Le travail porte principalement sur la stabilisation Windows, la cohérence des policies, la couverture de tests, la documentation et le durcissement des surfaces déjà présentes.

### Futur

Aucun calendrier public ou engagement de compatibilité n’est défini dans le dépôt. Les automatisations navigateur et bureau, l’exécution MCP/A2A et les providers directs non actifs doivent rester considérés comme expérimentaux ou incomplets tant que leur implémentation et leurs tests ne sont pas finalisés.

## Licence

License: to be defined.

Le dépôt ne contient actuellement aucun fichier `LICENSE`, `LICENSE.md` ou `COPYING`.
