import type {
  AbstentionReason,
  FreshnessStatus,
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
  timeZone: "Europe/Paris",
});

export function formatDecimal(value: string | number) {
  return decimalFormatter.format(Number(value));
}

export function formatPercent(value: string | number) {
  return percentFormatter.format(Number(value));
}

export function formatSignedPercent(value: string | number) {
  const numericValue = Number(value);
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
  return dateFormatter.format(new Date(value));
}

export function formatTimeUntil(startsAt: string, referenceTime: string) {
  const milliseconds = new Date(startsAt).getTime() - new Date(referenceTime).getTime();
  if (milliseconds <= 0) {
    return "Déjà commencé";
  }

  const totalMinutes = Math.ceil(milliseconds / 60_000);
  if (totalMinutes < 60) {
    return `Dans ${totalMinutes.toString()} min`;
  }

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes === 0
    ? `Dans ${hours.toString()} h`
    : `Dans ${hours.toString()} h ${minutes.toString()} min`;
}

export function isAdmissible(opportunity: Opportunity, referenceTime: string) {
  return (
    opportunity.quality.publishable &&
    opportunity.meta.freshness === "fresh" &&
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

export function describeOpportunity(opportunity: Opportunity) {
  if (opportunity.quality.publishable) {
    return "Signal admissible : les contrôles de qualité et de fraîcheur sont satisfaits.";
  }

  const reasons = opportunity.quality.abstentionReasons ?? [];
  if (reasons.length === 0) {
    return "Signal non publiable selon la politique de décision active.";
  }

  return formatAbstentionReasons(reasons).join(" · ");
}
