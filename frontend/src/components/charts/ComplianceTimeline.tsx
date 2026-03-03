"use client";

import { useState, useRef, useEffect } from "react";
import type { Evaluation } from "@/lib/types";
import { truncateSha } from "@/lib/utils";

interface ComplianceTimelineProps {
  evaluations: Evaluation[];
}

interface TimelineNode {
  date: string;
  fullDate: string;
  risk_score: number;
  decision: "PASS" | "REVIEW_REQUIRED" | "FAIL";
  commit_sha: string;
  pr_number?: number;
  lines_added?: number;
  lines_deleted?: number;
}

const nodeColor: Record<string, string> = {
  PASS: "#34D399",
  REVIEW_REQUIRED: "#FBBF24",
  FAIL: "#F87171",
};

const glowColor: Record<string, string> = {
  PASS: "rgba(52, 211, 153, 0.25)",
  REVIEW_REQUIRED: "rgba(251, 191, 36, 0.20)",
  FAIL: "rgba(248, 113, 113, 0.25)",
};

const labelColor: Record<string, string> = {
  PASS: "text-status-pass",
  REVIEW_REQUIRED: "text-status-review",
  FAIL: "text-status-fail",
};

const labelText: Record<string, string> = {
  PASS: "Pass",
  REVIEW_REQUIRED: "Review",
  FAIL: "Fail",
};

export default function ComplianceTimeline({ evaluations }: ComplianceTimelineProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const nodes: TimelineNode[] = [...evaluations]
    .sort((a, b) => new Date(a.evaluated_at).getTime() - new Date(b.evaluated_at).getTime())
    .map((ev) => ({
      date: new Date(ev.evaluated_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      fullDate: new Date(ev.evaluated_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }),
      risk_score: ev.risk_score,
      decision: ev.decision,
      commit_sha: ev.commit_sha,
      pr_number: ev.pr_number,
      lines_added: ev.lines_added,
      lines_deleted: ev.lines_deleted,
    }));

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, []);

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-text-light-muted dark:text-text-muted">
        No evaluation history yet
      </div>
    );
  }

  const nodeSpacing = 120;
  const svgWidth = Math.max(nodes.length * nodeSpacing + 60, 400);
  const trackY = 50;
  const nodeRadius = 10;
  const glowRadius = 18;

  return (
    <div className="relative">
      <div ref={scrollRef} className="overflow-x-auto pb-2 -mx-1 px-1">
        <div style={{ minWidth: svgWidth }} className="relative">
          <svg
            width={svgWidth}
            height={130}
            className="block"
            viewBox={`0 0 ${svgWidth} 130`}
          >
            <line
              x1={30}
              y1={trackY}
              x2={svgWidth - 30}
              y2={trackY}
              className="stroke-border-light dark:stroke-white/8"
              strokeWidth={2}
              strokeLinecap="round"
            />

            {nodes.map((node, i) => {
              const cx = 30 + i * nodeSpacing + nodeSpacing / 2;
              const isHovered = hoveredIdx === i;
              const color = nodeColor[node.decision];
              const glow = glowColor[node.decision];

              return (
                <g key={i}>
                  {i < nodes.length - 1 && (
                    <line
                      x1={cx}
                      y1={trackY}
                      x2={cx + nodeSpacing}
                      y2={trackY}
                      stroke={color}
                      strokeWidth={2}
                      strokeOpacity={0.3}
                    />
                  )}

                  <circle
                    cx={cx}
                    cy={trackY}
                    r={isHovered ? glowRadius + 4 : glowRadius}
                    fill={glow}
                    className="transition-all duration-200"
                  />
                  <circle
                    cx={cx}
                    cy={trackY}
                    r={isHovered ? nodeRadius + 2 : nodeRadius}
                    fill={color}
                    className="transition-all duration-200 cursor-pointer"
                    stroke={isHovered ? color : "transparent"}
                    strokeWidth={isHovered ? 3 : 0}
                    strokeOpacity={0.3}
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  />

                  <text
                    x={cx}
                    y={trackY + 30}
                    textAnchor="middle"
                    className="fill-text-light-secondary dark:fill-text-secondary text-[11px]"
                    style={{ fontSize: 11 }}
                  >
                    {node.date}
                  </text>

                  <text
                    x={cx}
                    y={trackY + 46}
                    textAnchor="middle"
                    className="fill-text-light-muted dark:fill-text-muted"
                    style={{ fontSize: 9, fontFamily: "ui-monospace, monospace" }}
                  >
                    {truncateSha(node.commit_sha)}
                  </text>

                  <text
                    x={cx}
                    y={trackY - 20}
                    textAnchor="middle"
                    className="font-bold"
                    style={{ fontSize: 13 }}
                    fill={color}
                  >
                    {node.risk_score}
                  </text>
                </g>
              );
            })}
          </svg>

          {hoveredIdx !== null && nodes[hoveredIdx] && (
            <TimelineTooltip
              node={nodes[hoveredIdx]}
              x={30 + hoveredIdx * nodeSpacing + nodeSpacing / 2}
              scrollLeft={scrollRef.current?.scrollLeft ?? 0}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function TimelineTooltip({
  node,
  x,
  scrollLeft,
}: {
  node: TimelineNode;
  x: number;
  scrollLeft: number;
}) {
  const color = nodeColor[node.decision];

  return (
    <div
      className="absolute z-50 pointer-events-none animate-scale-in"
      style={{
        left: x - scrollLeft,
        top: 0,
        transform: "translate(-50%, -8px)",
      }}
    >
      <div className="rounded-lg border border-border-light dark:border-border-dark bg-bg-light-surface dark:bg-bg-elevated p-3 shadow-lg text-xs space-y-2 min-w-[170px]">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-text-light-primary dark:text-text-primary">{node.fullDate}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
          <span className={`font-medium ${labelColor[node.decision]}`}>
            {labelText[node.decision]}
          </span>
          {node.pr_number && (
            <span className="text-accent dark:text-accent-secondary ml-auto">#{node.pr_number}</span>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-light-muted dark:text-text-muted">Risk Score</span>
          <span className="font-bold text-text-light-primary dark:text-text-primary tabular-nums">{node.risk_score}</span>
        </div>
        {(node.lines_added !== undefined || node.lines_deleted !== undefined) && (
          <div className="flex items-center gap-3 pt-1.5 border-t border-border-light dark:border-border-dark">
            <span className="text-text-light-muted dark:text-text-muted text-[10px]">Lines</span>
            <span className="text-status-pass font-semibold tabular-nums">+{node.lines_added ?? 0}</span>
            <span className="text-status-fail font-semibold tabular-nums">-{node.lines_deleted ?? 0}</span>
          </div>
        )}
      </div>
    </div>
  );
}
