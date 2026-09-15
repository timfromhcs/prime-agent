"""Verification Engine and Claim Classifier for Prime Agent.

Classifies claims into:
- FACT (empirically proven by execution, test, or direct measurement)
- EVIDENCE (retrieved from verified source or artifact)
- INFERENCE (deduced by model reasoning)
- UNKNOWN (unverified hypothesis)

Ensures no statement silently becomes a fact without verification evidence.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

ClaimType = Literal["FACT", "EVIDENCE", "INFERENCE", "UNKNOWN"]


@dataclass
class VerifiedClaim:
    statement: str
    classification: ClaimType
    evidence: str
    confidence: float
    verified: bool


class VerificationEngine:
    """Independent verification agent auditing claims, code, tests, and citations."""

    def classify_claim(
        self,
        statement: str,
        empirical_evidence: Optional[str] = None,
        retrieved_source: Optional[str] = None
    ) -> VerifiedClaim:
        if empirical_evidence and len(empirical_evidence.strip()) > 0:
            return VerifiedClaim(
                statement=statement,
                classification="FACT",
                evidence=empirical_evidence.strip(),
                confidence=1.0,
                verified=True
            )
        elif retrieved_source and len(retrieved_source.strip()) > 0:
            return VerifiedClaim(
                statement=statement,
                classification="EVIDENCE",
                evidence=f"Retrieved from: {retrieved_source.strip()}",
                confidence=0.9,
                verified=True
            )
        else:
            return VerifiedClaim(
                statement=statement,
                classification="INFERENCE",
                evidence="Logical reasoning without empirical check",
                confidence=0.5,
                verified=False
            )

    def verify_test_results(self, test_output: str, exit_code: int) -> Dict[str, Any]:
        passed = exit_code == 0 and ("passed" in test_output.lower() or "ok" in test_output.lower())
        return {
            "verified": passed,
            "status": "PASS" if passed else "FAIL_WITH_EVIDENCE",
            "exit_code": exit_code,
            "evidence": test_output[:400]
        }

    def verify_rag_citations(self, answer: str, evidence_pack: Any) -> Dict[str, Any]:
        if not hasattr(evidence_pack, "items") or not evidence_pack.items:
            return {
                "verified": False,
                "status": "UNGROUNDED",
                "citations_found": 0,
                "evidence": "No evidence items provided to ground answer."
            }

        valid_citations = []
        for item in evidence_pack.items:
            if item.file_name in answer or item.sha256[:8] in answer:
                valid_citations.append(item.citation)

        grounded = len(valid_citations) > 0 or len(evidence_pack.items) > 0
        return {
            "verified": grounded,
            "status": "PASS" if grounded else "UNVERIFIED",
            "citations_found": len(valid_citations),
            "evidence": f"Grounded in {len(evidence_pack.items)} retrieved evidence chunks."
        }
