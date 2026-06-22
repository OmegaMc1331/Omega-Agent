from __future__ import annotations

from omega_agent.connectors.base import ConnectorOperation


def github_operations(connector_id: str = "github") -> list[ConnectorOperation]:
    operations = [
        ("list_repos", "List repositories", "Liste les repositories accessibles."),
        ("get_repo", "Get repository", "Recupere un repository."),
        ("list_issues", "List issues", "Liste les issues d'un repository."),
        ("get_issue", "Get issue", "Recupere une issue."),
        ("list_pull_requests", "List pull requests", "Liste les pull requests."),
        ("get_pull_request", "Get pull request", "Recupere une pull request."),
    ]
    return [
        ConnectorOperation(
            id=operation_id,
            connector_id=connector_id,
            name=name,
            description=description,
            input_schema={"type": "object", "properties": {}},
            risk_level="medium",
            requires_approval_default=False,
            action_category="read_only",
            enabled=True,
        )
        for operation_id, name, description in operations
    ]
