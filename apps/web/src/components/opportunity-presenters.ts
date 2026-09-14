import type {
  AbstentionReason,
  FreshnessStatus,
  OddsSnapshot,
  Opportunity,
  ValueGrade,
} from "@metiquo/contracts/types";

export type OpportunitySort = "conservative-ev-desc" | "start-asc";

export const gradeLabels = {
  BLOCKED: "Bloqué",
  NO_EDGE: "Sans edge",
  STRONG_VALUE: "Forte value",
  VALUE: "Value",
  WATCH: "À surveiller",
} satisfies Record<ValueGrade, string>;

export const freshnessLabels = {
  degraded: "Dégradée",
  failed: "Échec",
  fresh: "À jour",
  quarantined: "Quarantaine",
  stale: "Ancienne",
} satisfies Record<FreshnessStatus, string>;

export const abstentionLabels = {
  CALIBRATION_FAILED: "Calibration non validée",
  CAPABILITY_DISABLED: "Capacité désactivée",
  CONSERVATIVE_EV_NEGATIVE: "EV prudente négative",
  CONSERVATIVE_EV_TOO_SMALL: "EV prudente insuffisante",
  EDGE_TOO_SMALL: "Edge insuffisant",
  EVENT_ALREADY_STARTED: "Match déjà commencé",
  EVENT_MAPPING_AMBIGUOUS: "Mapping de l’événement ambigu",
  EXPECTED_VALUE_TOO_SMALL: "EV insuffisante",
  INSUFFICIENT_HISTORY: "Historique insuffisant",
  LIVE_BETTING_OUT_OF_SCOPE: "Marché live hors périmètre",
  MARKET_OUTCOMES_INCOMPLETE: "Issues du marché incomplètes",
  MARKET_RULES_UNKNOWN: "Règles du marché inconnues",
  MARKET_SUSPENDED: "Marché suspendu",
  MODEL_STALE: "Modèle ancien",
  ODDS_INFORMATIONAL_ONLY: "Cote informative uniquement",
  ODDS_STALE: "Cote trop ancienne",
  ODDS_TEMPORAL_ORDER_INVALID: "Chronologie de la cote invalide",
  OUT_OF_DISTRIBUTION: "Incertitude hors distribution",
  PATCH_CONTEXT_UNKNOWN: "Contexte de patch inconnu",
  ROSTER_UNCERTAIN: "Roster incertain",
  SELECTION_MISSING: "Sélection absente",
  SOURCE_STALE: "Source de données ancienne",
} satisfies Readonly<Record<AbstentionReason, string>>;

export function formatAbstentionReason(reason: AbstentionReason) {
  return abstentionLabels[reason];
}

export function formatAbstentionReasons(reasons: readonly AbstentionReason[]) {
  return reasons.map(formatAbstentionReason);
}

const decimalFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 1,
  style: "percent",
});

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "Europe/Paris",
});

export function formatDecimal(value: string | number) {
  const number = Number(value);
  return Number.isFinite(number) ? decimalFormatter.format(number) : "Indisponible";
}

export function formatPercent(value: string | number) {
  const number = Number(value);
  return Number.isFinite(number) ? percentFormatter.format(number) : "Indisponible";
}

export function formatSignedPercent(value: string | number) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "Indisponible";
  const formattedValue = percentFormatter.format(Math.abs(numericValue));
  if (numericValue > 0) {
    return `+${formattedValue}`;
  }
  if (numericValue < 0) {
    return `−${formattedValue}`;
  }
  return formattedValue;
}

export function formatDateTime(value: string) {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? dateFormatter.format(date) : "Date indisponible";
}

export function formatTimeUntil(startsAt: string, referenceTime: string) {
  const milliseconds = new Date(startsAt).getTime() - new Date(referenceTime).getTime();
  if (!Number.isFinite(milliseconds)) return "Échéance indisponible";
  if (milliseconds <= 0) {
    return "Déjà commencé";
  }

  const totalMinutes = Math.ceil(milliseconds / 60_000);
  if (totalMinutes < 60) {
    return `Dans ${totalMinutes.toString()} min`;
  }

  const hours = Math.floor(totalMinutes / 60);
  if (hours >= 48) {
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    return `Dans ${String(days)} j${remainingHours ? ` ${String(remainingHours)} h` : ""}`;
  }
  const minutes = totalMinutes % 60;
  return minutes === 0
    ? `Dans ${hours.toString()} h`
    : `Dans ${hours.toString()} h ${minutes.toString()} min`;
}

export function isAdmissible(opportunity: Opportunity, referenceTime: string) {
  return (
    opportunity.quality.publishable &&
    ["VALUE", "STRONG_VALUE"].includes(opportunity.value.grade) &&
    opportunity.quality.sourceFreshness === "fresh" &&
    !opportunity.book.informationalOnly &&
    opportunity.meta.freshness === "fresh" &&
    opportunity.book.marketStatus === "open" &&
    opportunity.market.status === "open" &&
    opportunity.event.status === "scheduled" &&
    new Date(opportunity.event.startsAt).getTime() > new Date(referenceTime).getTime()
  );
}

export function sortOpportunities(opportunities: readonly Opportunity[], sort: OpportunitySort) {
  return [...opportunities].sort((left, right) => {
    const difference =
      sort === "start-asc"
        ? new Date(left.event.startsAt).getTime() - new Date(right.event.startsAt).getTime()
        : Number(right.value.conservativeExpectedValue) -
          Number(left.value.conservativeExpectedValue);

    return difference === 0 ? left.signalId.localeCompare(right.signalId) : difference;
  });
}

export function matchingOddsSnapshots(
  opportunity: Opportunity,
  snapshots: readonly OddsSnapshot[] | undefined,
) {
  return [...(snapshots ?? [])]
    .filter(
      (snapshot) =>
        snapshot.marketId === opportunity.book.marketId &&
        snapshot.selection === opportunity.book.selection,
    )
    .sort((left, right) => {
      const byTime = left.capturedAt.localeCompare(right.capturedAt);
      return byTime === 0 ? left.oddsSnapshotId.localeCompare(right.oddsSnapshotId) : byTime;
    });
}

export function latestMatchingOddsSnapshot(
  opportunity: Opportunity,
  snapshots: readonly OddsSnapshot[] | undefined,
) {
  return matchingOddsSnapshots(opportunity, snapshots).at(-1);
}

export function newerOddsSnapshot(
  opportunity: Opportunity,
  snapshots: readonly OddsSnapshot[] | undefined,
) {
  const latest = latestMatchingOddsSnapshot(opportunity, snapshots);
  return latest &&
    latest.oddsSnapshotId !== opportunity.book.oddsSnapshotId &&
    latest.capturedAt > opportunity.book.capturedAt
    ? latest
    : undefined;
}

export function describeOpportunity(
  opportunity: Opportunity,
  referenceTime = opportunity.meta.computedAt,
) {
  if (opportunity.event.status === "cancelled")
    return "Match annulé : aucune entrée paper possible.";
  if (opportunity.event.status === "finished")
    return "Match terminé : aucune entrée paper possible.";
  if (
    opportunity.event.status === "live" ||
    new Date(opportunity.event.startsAt).getTime() <= new Date(referenceTime).getTime()
  ) {
    return "Match déjà commencé : aucune entrée paper possible.";
  }
  if (opportunity.meta.freshness !== "fresh" || opportunity.quality.sourceFreshness !== "fresh")
    return "Fraîcheur insuffisante : actualiser les données avant toute décision.";
  if (opportunity.book.informationalOnly)
    return "Cote informative uniquement : aucune entrée paper possible.";
  if (opportunity.market.status !== "open" || opportunity.book.marketStatus !== "open")
    return "Marché fermé ou suspendu : aucune entrée paper possible.";
  if (isAdmissible(opportunity, referenceTime)) {
    return "Signal admissible : les contrôles de qualité et de fraîcheur sont satisfaits.";
  }

  const reasons = opportunity.quality.abstentionReasons ?? [];
  if (reasons.length === 0) {
    if (!["VALUE", "STRONG_VALUE"].includes(opportunity.value.grade))
      return "Avantage estimé insuffisant : ce signal reste consultable, mais ne permet pas de créer une décision paper.";
    return "Signal non publiable selon la politique de décision active.";
  }

  return formatAbstentionReasons(reasons).join(" · ");
}
