import type { AbstentionReason, Opportunity } from "@metiquo/contracts/types";
import { describe, expect, it } from "vitest";

import {
  formatSignedPercent,
  formatAbstentionReasons,
  formatTimeUntil,
  isAdmissible,
  sortOpportunities,
} from "./opportunity-presenters";

function opportunity(overrides: {
  conservativeExpectedValue: string;
  signalId: string;
  startsAt: string;
}): Opportunity {
  return {
    book: {
      ageSeconds: 5,
      capturedAt: "2026-09-04T12:00:00Z",
      decimalOdds: "2.00",
      eventId: "event",
      marketId: "market",
      marketStatus: "open",
      noVigProbability: "0.50",
      oddsSnapshotId: "odds",
      provenanceReference: "test",
      provider: "mock",
      providerStatus: "operational",
      rawImpliedProbability: "0.50",
      selection: "TEAM_B",
    },
    event: {
      bestOf: 3,
      competition: "Ligue Test",
      eventId: "event",
      gameTitle: "lol",
      observedAt: "2026-09-04T12:00:00Z",
      startsAt: overrides.startsAt,
      status: "scheduled",
      teamA: "Aurore",
      teamAId: "team-a",
      teamB: "Bastion",
      teamBId: "team-b",
    },
    explanationReference: "test",
    market: {
      eventId: "event",
      marketId: "market",
      period: "SERIES",
      selection: "TEAM_B",
      selectionLabel: "Bastion",
      status: "open",
      type: "MATCH_WINNER",
    },
    meta: {
      appVersion: "0.1.0",
      asOf: "2026-09-04T12:00:00Z",
      computedAt: "2026-09-04T12:00:00Z",
      dataMode: "mock",
      freshness: "fresh",
    },
    model: {
      confidence: "0.80",
      createdAt: "2026-09-04T12:00:00Z",
      dataCoverage: "0.90",
      eventId: "event",
      featureSnapshotId: "features",
      marketId: "market",
      modelVersion: "v1",
      modelVersionId: "model",
      outOfDistributionDistance: "0.10",
      predictionCutoff: "2026-09-04T11:59:00Z",
      predictionId: "prediction",
      probability: "0.60",
      probabilityHigh: "0.65",
      probabilityLow: "0.55",
      selection: "TEAM_B",
    },
    quality: {
      dataCoverage: "0.90",
      mappingConfidence: "0.99",
      modelStatus: "champion",
      publishable: true,
      sourceFreshness: "fresh",
    },
    signalId: overrides.signalId,
    value: {
      conservativeExpectedValue: overrides.conservativeExpectedValue,
      edge: "0.10",
      expectedValue: "0.20",
      fairOdds: "1.67",
      grade: "VALUE",
      policyVersion: "test-value-policy-v1",
    },
  };
}

describe("opportunity presenters", () => {
  it("sorts by conservative EV by default with a stable signal tie-breaker", () => {
    const lower = opportunity({
      conservativeExpectedValue: "0.04",
      signalId: "b",
      startsAt: "2026-09-04T16:00:00Z",
    });
    const higherB = opportunity({
      conservativeExpectedValue: "0.08",
      signalId: "b",
      startsAt: "2026-09-04T17:00:00Z",
    });
    const higherA = opportunity({
      conservativeExpectedValue: "0.08",
      signalId: "a",
      startsAt: "2026-09-04T18:00:00Z",
    });

    expect(
      sortOpportunities([lower, higherB, higherA], "conservative-ev-desc").map(
        (item) => item.signalId,
      ),
    ).toEqual(["a", "b", "b"]);
    expect(sortOpportunities([higherB, lower], "start-asc")[0]?.signalId).toBe("b");
  });

  it("requires freshness, open state and a future start for admissibility", () => {
    const candidate = opportunity({
      conservativeExpectedValue: "0.08",
      signalId: "candidate",
      startsAt: "2026-09-04T16:00:00Z",
    });

    expect(isAdmissible(candidate, "2026-09-04T12:00:00Z")).toBe(true);
    expect(isAdmissible(candidate, "2026-09-04T17:00:00Z")).toBe(false);
    expect(
      isAdmissible(
        { ...candidate, meta: { ...candidate.meta, freshness: "stale" } },
        candidate.meta.computedAt,
      ),
    ).toBe(false);
  });

  it("formats signed values and relative start times without relying on color", () => {
    expect(formatSignedPercent("0.08")).toContain("+8,0");
    expect(formatSignedPercent("-0.02")).toContain("−2,0");
    expect(formatTimeUntil("2026-09-04T14:30:00Z", "2026-09-04T12:00:00Z")).toBe("Dans 2 h 30 min");
  });

  it("shows every normative abstention as an ordered human-readable reason", () => {
    const reasons: AbstentionReason[] = [
      "ODDS_STALE",
      "MARKET_SUSPENDED",
      "EVENT_MAPPING_AMBIGUOUS",
      "INSUFFICIENT_HISTORY",
      "ROSTER_UNCERTAIN",
      "SOURCE_STALE",
      "MODEL_STALE",
      "OUT_OF_DISTRIBUTION",
      "CALIBRATION_FAILED",
      "EDGE_TOO_SMALL",
      "CONSERVATIVE_EV_NEGATIVE",
      "MARKET_RULES_UNKNOWN",
      "PATCH_CONTEXT_UNKNOWN",
      "EVENT_ALREADY_STARTED",
      "CAPABILITY_DISABLED",
    ];

    const labels = formatAbstentionReasons(reasons);

    expect(labels).toHaveLength(reasons.length);
    expect(labels[0]).toBe("Cote trop ancienne");
    expect(labels.at(-1)).toBe("Capacité désactivée");
    expect(labels.join(" · ")).not.toContain("ODDS_STALE");
  });
});
