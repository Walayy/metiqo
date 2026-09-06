"""Inventaire sans filtre de résultat des preuves financières connues."""

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from metiquo.db.odds_models import OddsSnapshotRecord
from metiquo.db.paper_models import PaperBetRecord, PaperSettlementRecord
from metiquo.db.pricing_models import (
    SignalRecord,
    ValueEvaluationRecord,
    ValuePolicyAuditRecord,
    ValuePolicyRecord,
)
from metiquo.paper.creation import decimal_text

AUDIT_METHOD_VERSION = "complete-paper-audit-v1"
_ELIGIBLE = frozenset({"VALUE", "STRONG_VALUE"})


def reporting_audit(session: Session, *, now: datetime, currency: str) -> dict[str, object]:
    """Lectures groupées dans la transaction cohérente du rapport propriétaire.

    L'inventaire des signaux est global : un signal n'a pas de devise. Seuls les
    montants, entrées et règlements du rapport sont limités à la devise demandée.
    """
    signals = session.scalars(
        select(SignalRecord)
        .where(SignalRecord.computed_at <= now)
        .order_by(SignalRecord.computed_at, SignalRecord.id)
    ).all()
    evaluations = session.scalars(
        select(ValueEvaluationRecord)
        .where(ValueEvaluationRecord.computed_at <= now)
        .order_by(ValueEvaluationRecord.computed_at, ValueEvaluationRecord.id)
    ).all()
    all_bets = session.scalars(
        select(PaperBetRecord)
        .where(PaperBetRecord.placed_at <= now)
        .order_by(PaperBetRecord.placed_at, PaperBetRecord.id)
    ).all()
    taken = {b.signal_id: b for b in all_bets}
    rechecks = {str(b.decision_evidence.get("entryEvaluationId")) for b in all_bets}
    rechecked_signals = {e.signal_id for e in evaluations if str(e.id) in rechecks}
    admitted_signals = {e.signal_id for e in evaluations if e.grade == "VALUE"}
    inventory: list[dict[str, object]] = []
    for signal in signals:
        bet = taken.get(signal.id)
        if bet is not None:
            disposition = "taken"
        elif signal.id in rechecked_signals:
            disposition = "entry_recheck"
        elif signal.grade in _ELIGIBLE and signal.id in admitted_signals:
            disposition = "not_taken"
        else:
            disposition = "not_eligible"
        inventory.append(
            {
                "signalId": str(signal.id),
                "fingerprint": signal.signal_fingerprint,
                "computedAt": signal.computed_at.isoformat(),
                "policyVersion": signal.policy_version,
                "grade": signal.grade,
                "reasons": signal.abstention_reasons,
                "oddsSnapshotId": str(signal.odds_snapshot_id),
                "offeredOdds": decimal_text(signal.offered_odds),
                "predictionId": str(signal.prediction_id),
                "expectedValue": decimal_text(signal.expected_value)
                if signal.expected_value is not None
                else None,
                "conservativeExpectedValue": decimal_text(signal.conservative_expected_value)
                if signal.conservative_expected_value is not None
                else None,
                "selectedTeamId": str(signal.selected_team_id) if signal.selected_team_id else None,
                "paperDisposition": disposition,
                "paperBetId": str(bet.id) if bet else None,
                "paperCurrency": bet.currency if bet else None,
            }
        )
    bets = tuple(b for b in all_bets if b.currency == currency)
    bet_ids = tuple(b.id for b in bets)
    signal_map = {s.id: s for s in signals}
    entries = [
        {
            "paperBetId": str(b.id),
            "signalId": str(b.signal_id),
            "actor": b.actor,
            "placedAt": b.placed_at.isoformat(),
            "decisionEvidence": b.decision_evidence,
            "signalOdds": decimal_text(signal_map[b.signal_id].offered_odds),
            "entryOdds": decimal_text(b.entry_odds),
            "slippageRatio": decimal_text(b.entry_odds / signal_map[b.signal_id].offered_odds - 1),
            "slippageMethod": "exact-signal-snapshot-v1",
        }
        for b in bets
    ]
    history: list[dict[str, object]] = []
    prior_pnl: dict[UUID, Decimal] = defaultdict(Decimal)
    for revision in session.scalars(
        select(PaperSettlementRecord)
        .where(
            PaperSettlementRecord.paper_bet_id.in_(bet_ids),
            PaperSettlementRecord.occurred_at <= now,
        )
        .order_by(PaperSettlementRecord.paper_bet_id, PaperSettlementRecord.revision)
    ):
        current = revision.profit_loss or Decimal()
        history.append(
            {
                "paperBetId": str(revision.paper_bet_id),
                "settlementId": str(revision.id),
                "revision": revision.revision,
                "supersedesId": str(revision.supersedes_id) if revision.supersedes_id else None,
                "occurredAt": revision.occurred_at.isoformat(),
                "status": revision.status,
                "profitLoss": decimal_text(revision.profit_loss)
                if revision.profit_loss is not None
                else None,
                "profitLossAdjustment": decimal_text(current - prior_pnl[revision.paper_bet_id]),
                "actor": revision.actor,
                "reason": revision.reason,
                "resultSnapshotId": str(revision.result_snapshot_id)
                if revision.result_snapshot_id
                else None,
                "rulesVersion": revision.settlement_rules_version,
                "requestFingerprint": revision.request_fingerprint,
                "evidence": revision.evidence,
            }
        )
        prior_pnl[revision.paper_bet_id] = current
    # Toutes les observations des sélections des signaux, pertes et abstentions incluses.
    selection_ids = select(OddsSnapshotRecord.selection_id).where(
        OddsSnapshotRecord.id.in_(tuple(s.odds_snapshot_id for s in signals))
    )
    odds_history: list[dict[str, object]] = [
        {
            "oddsSnapshotId": str(q.id),
            "selectionId": str(q.selection_id),
            "marketId": str(q.market_id),
            "decimalOdds": decimal_text(q.decimal_odds),
            "capturedAt": q.captured_at.isoformat() if q.captured_at else None,
            "recordedAt": q.recorded_at.isoformat(),
            "timestampReliable": q.timestamp_reliable,
            "informationalOnly": q.informational_only,
            "marketStatus": q.market_status,
            "fingerprint": q.observation_fingerprint,
        }
        for q in session.scalars(
            select(OddsSnapshotRecord)
            .where(
                OddsSnapshotRecord.selection_id.in_(selection_ids),
                OddsSnapshotRecord.recorded_at <= now,
            )
            .order_by(OddsSnapshotRecord.recorded_at, OddsSnapshotRecord.id)
        )
    ]
    previous_quotes: dict[str, dict[str, object]] = {}
    for observation in odds_history:
        selection_id = str(observation["selectionId"])
        previous = previous_quotes.get(selection_id)
        observation["previousSnapshotId"] = previous["oddsSnapshotId"] if previous else None
        observation["changeFromPreviousRatio"] = (
            decimal_text(
                Decimal(str(observation["decimalOdds"])) / Decimal(str(previous["decimalOdds"])) - 1
            )
            if previous
            else None
        )
        previous_quotes[selection_id] = observation
    versions = {s.policy_version for s in signals} | {e.policy_version for e in evaluations}
    policies = session.scalars(
        select(ValuePolicyRecord)
        .where(ValuePolicyRecord.version.in_(versions), ValuePolicyRecord.created_at <= now)
        .order_by(ValuePolicyRecord.version)
    ).all()
    policy_changes = [
        {
            "auditId": str(p.id),
            "policyId": str(p.policy_id),
            "previousPolicyId": str(p.previous_policy_id) if p.previous_policy_id else None,
            "actor": p.actor,
            "reason": p.reason,
            "occurredAt": p.occurred_at.isoformat(),
            "changes": p.changes,
        }
        for p in session.scalars(
            select(ValuePolicyAuditRecord)
            .where(
                ValuePolicyAuditRecord.policy_id.in_(tuple(p.id for p in policies)),
                ValuePolicyAuditRecord.occurred_at <= now,
            )
            .order_by(ValuePolicyAuditRecord.occurred_at, ValuePolicyAuditRecord.id)
        )
    ]
    return {
        "methodVersion": AUDIT_METHOD_VERSION,
        "signalScope": "all currencies; physical signals, entry rechecks identified separately",
        "counts": dict(Counter(str(s["paperDisposition"]) for s in inventory)),
        "signals": inventory,
        "earlyAbstentions": [
            {
                "evaluationId": str(e.id),
                "policyVersion": e.policy_version,
                "computedAt": e.computed_at.isoformat(),
                "grade": e.grade,
                "reasons": e.abstention_reasons,
                "fingerprint": e.fingerprint,
                "evidence": e.evidence,
            }
            for e in evaluations
            if e.signal_id is None
        ],
        "entries": entries,
        "oddsHistory": odds_history,
        "settlementHistory": history,
        "policies": [
            {
                "policyId": str(p.id),
                "version": p.version,
                "fingerprint": p.fingerprint,
                "tunedThrough": p.tuned_through.isoformat(),
                "finalTestStartsAt": p.final_test_starts_at.isoformat(),
                "minEdge": decimal_text(p.min_edge),
                "minEv": decimal_text(p.min_ev),
                "minConservativeEv": decimal_text(p.min_conservative_ev),
                "maxOddsAgeSeconds": p.max_odds_age_seconds,
                "minMappingConfidence": decimal_text(p.min_mapping_confidence),
                "overrides": p.overrides,
            }
            for p in policies
        ],
        "policyChanges": policy_changes,
    }
