import type { Decision, DataClassification, ControlStatus } from "./types";

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function truncateSha(sha: string, len = 7): string {
  return sha.slice(0, len);
}

export function decisionColor(decision: Decision): string {
  switch (decision) {
    case "PASS":
      return "text-status-pass";
    case "REVIEW_REQUIRED":
      return "text-status-review";
    case "FAIL":
      return "text-status-fail";
  }
}

export function decisionBgColor(decision: Decision): string {
  switch (decision) {
    case "PASS":
      return "bg-status-pass/15 text-status-pass";
    case "REVIEW_REQUIRED":
      return "bg-status-review/15 text-status-review";
    case "FAIL":
      return "bg-status-fail/15 text-status-fail";
  }
}

export function decisionDotColor(decision: Decision): string {
  switch (decision) {
    case "PASS":
      return "#34D399";
    case "REVIEW_REQUIRED":
      return "#FBBF24";
    case "FAIL":
      return "#F87171";
  }
}

export function decisionLabel(decision: Decision): string {
  switch (decision) {
    case "PASS":
      return "Pass";
    case "REVIEW_REQUIRED":
      return "Review Required";
    case "FAIL":
      return "Fail";
  }
}

export function classificationColor(c: DataClassification): string {
  switch (c) {
    case "public":
      return "bg-blue-500/15 text-blue-400";
    case "internal":
      return "bg-slate-500/15 text-slate-400";
    case "confidential":
      return "bg-amber-500/15 text-amber-400";
    case "restricted":
      return "bg-red-500/15 text-red-400";
  }
}

export function controlStatusColor(s: ControlStatus): string {
  switch (s) {
    case "planned":
      return "bg-slate-500/15 text-slate-400";
    case "implemented":
      return "bg-blue-500/15 text-blue-400";
    case "verified":
      return "bg-status-pass/15 text-status-pass";
  }
}

export function riskScoreColor(score: number): string {
  if (score <= 30) return "text-status-pass";
  if (score <= 69) return "text-status-review";
  return "text-status-fail";
}
