"""Granular permission engine: allow|ask|deny scoped by tool/path/command/agent/session/project.

Deny rules win. Sensitive paths (.env, credentials, keys, tokens) default to ask/deny.
Decisions are auditable; session-scoped allows can be granted at runtime.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


SENSITIVE_PATTERNS = [
    "*.env", ".env*", "*credentials*", "*secret*", "*token*",
    "*.pem", "*.key", "id_rsa*", "*password*",
]

DESTRUCTIVE_COMMAND_PATTERNS = [
    "rm -rf /*", "rm -rf ~*", "mkfs*", ":(){:|:&};*",
    "*--force*push*", "git push --force*",
    "del /f /s /q C:\\*",
]


@dataclass
class PermissionRule:
    scope: str  # tool|path|command|agent|session|project
    pattern: str
    action: str  # allow|ask|deny


class PermissionEngine:
    def __init__(self, policy_file: str = "config/permissions.json"):
        self.policy_file = Path(policy_file)
        self.rules: List[PermissionRule] = []
        self.session_allows: Dict[str, List[str]] = {}  # session_id -> [pattern]
        self.audit: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.policy_file.exists():
            try:
                data = json.loads(self.policy_file.read_text(encoding="utf-8"))
                self.rules = [PermissionRule(**r) for r in data.get("rules", [])]
                return
            except Exception:
                pass
        self.rules = [
            PermissionRule(scope="path", pattern=p, action="ask") for p in SENSITIVE_PATTERNS
        ] + [
            PermissionRule(scope="command", pattern=p, action="deny") for p in DESTRUCTIVE_COMMAND_PATTERNS
        ]
        self.save()

    def save(self) -> None:
        self.policy_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.policy_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"rules": [asdict(r) for r in self.rules]}, indent=2), encoding="utf-8")
        tmp.replace(self.policy_file)

    def add_rule(self, scope: str, pattern: str, action: str) -> PermissionRule:
        rule = PermissionRule(scope=scope, pattern=pattern, action=action)
        self.rules.append(rule)
        self.save()
        return rule

    def allow_session_pattern(self, session_id: str, pattern: str) -> None:
        self.session_allows.setdefault(session_id, []).append(pattern)

    def _match(self, value: str, pattern: str) -> bool:
        return fnmatch.fnmatchcase(value, pattern) or fnmatch.fnmatchcase(Path(value).name, pattern)

    def decide(self, action: str, target: str = "", session_id: str = "",
               agent: str = "", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return {decision, reason, risk, matched_rule}."""
        candidates = [action, target, f"{action}:{target}"]
        decision = "allow"
        reason = "no matching rule; default allow for non-sensitive action"
        risk = "low"
        matched = None

        for rule in self.rules:
            hay = {"tool": action, "path": target, "command": target,
                   "agent": agent, "session": session_id}.get(rule.scope, "")
            if hay and self._match(hay, rule.pattern):
                matched = asdict(rule)
                decision = rule.action
                reason = f"matched {rule.scope}:{rule.pattern} -> {rule.action}"
                risk = "high" if rule.action == "deny" else ("medium" if rule.action == "ask" else "low")
                if rule.action == "deny":
                    break
        # explicit deny always wins; otherwise session allow can downgrade ask->allow
        if decision == "ask" and session_id:
            for pat in self.session_allows.get(session_id, []):
                if self._match(target, pat) or self._match(action, pat):
                    decision = "allow"
                    reason += f"; session-allowed via {pat}"
                    risk = "low"
                    break
        # sensitive-path escalation
        if decision == "allow" and target:
            for pat in SENSITIVE_PATTERNS:
                if self._match(target, pat):
                    decision = "ask"
                    reason = f"sensitive path {target} requires approval"
                    risk = "high"
                    matched = {"scope": "path", "pattern": pat, "action": "ask"}
                    break
        entry = {"action": action, "target": target, "session_id": session_id,
                 "agent": agent, "decision": decision, "reason": reason, "risk": risk}
        self.audit.append(entry)
        return {"decision": decision, "reason": reason, "risk": risk, "matched_rule": matched}

    def approval_card(self, action: str, target: str, reason: str, risk: str,
                      proposed_command: str = "") -> Dict[str, Any]:
        return {"action": action, "target": target, "reason": reason, "risk": risk,
                "proposed_command": proposed_command,
                "options": ["allow_once", "allow_session", "allow_pattern", "deny"]}
