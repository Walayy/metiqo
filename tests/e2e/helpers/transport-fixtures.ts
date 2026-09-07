import type {
  ItemResponsePaperMetricsDto,
  SystemStatusResponse,
} from "../../../packages/contracts/src/generated/types.gen.js";

// Synthetic transport fixtures, not measurements or financial validation.
export const operations: SystemStatusResponse = {
  status: "degraded",
  apiVersion: "0.1.0",
  dataMode: "real",
  generatedAt: "2026-09-08T03:00:00Z",
  dependencies: { database: { status: "available" } },
  operations: {
    readsAvailable: true,
    source: { status: "degraded", reasonCode: "SOURCE_TIMEOUT", asOf: "2026-09-08T02:00:00Z" },
    model: { status: "stale", trainingCutoff: "2026-07-08T02:00:00Z" },
    mappingBacklog: 3,
    jobCounts: { running: 1, queued: 2, failed: 1 },
    backups: { status: "not_configured" },
    metrics: {
      measuredJobCount: 2,
      meanJobDurationSeconds: 2.5,
      jobFailures: 1,
      processedRows: 12,
      anomalies: 4,
      blockingAnomalies: 2,
      signals: { VALUE: 1, BLOCKED: 2 },
      api: { requestCount: 8, failureCount: 1, meanLatencyMs: 3.4 },
    },
  },
};

export const financialReport: ItemResponsePaperMetricsDto = {
  data: {
    reportId: "aaaaaaaa-2222-4333-8444-555555555555",
    currency: "EUR",
    computedAt: "2026-09-07T12:00:00Z",
    methodVersion: "paper-finance-v1",
    reportFingerprint: "a".repeat(64),
    signals: 2,
    bets: 1,
    settled: 1,
    open: 0,
    pendingReview: 0,
    estimates: {
      profit_loss: { value: "-10", sampleSize: 1, unavailableReason: null },
      roi: { value: "-1", sampleSize: 1, unavailableReason: null },
      clv: { value: "-0.2", sampleSize: 1, unavailableReason: null },
      yield_ci_low: { value: null, sampleSize: 1, unavailableReason: "INSUFFICIENT_DAY_BLOCKS" },
    },
  },
  meta: {
    dataMode: "real",
    freshness: "fresh",
    asOf: "2026-09-07T12:00:00Z",
    computedAt: "2026-09-07T12:00:00Z",
    appVersion: "0.1.0",
  },
};
