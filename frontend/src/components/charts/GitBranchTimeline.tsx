"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import type { Evaluation, Decision } from "@/lib/types";
import { truncateSha } from "@/lib/utils";

const MAIN_Y = 22;
const FIRST_LANE = 56;
const LANE_GAP = 26;
const X_STEP = 100;
const LEFT_PAD = 40;
const RIGHT_PAD = 40;
const NODE_R = 6;
const MAIN_DOT_R = 3;

const decisionColor: Record<Decision, string> = {
  PASS: "#34D399",
  REVIEW_REQUIRED: "#FBBF24",
  FAIL: "#F87171",
};

const decisionGlow: Record<Decision, string> = {
  PASS: "rgba(52,211,153,0.25)",
  REVIEW_REQUIRED: "rgba(251,191,36,0.20)",
  FAIL: "rgba(248,113,113,0.25)",
};

const decisionLabel: Record<Decision, string> = {
  PASS: "Pass",
  REVIEW_REQUIRED: "Review",
  FAIL: "Fail",
};

interface ProcessedNode {
  eval: Evaluation;
  x: number;
  laneY: number;
  color: string;
  glow: string;
}

const DEFAULT_TIMELINE_POINTS = [
  { label: "D-2", state: "default" },
  { label: "D-1", state: "default" },
  { label: "Today", state: "default" },
];

export default function GitBranchTimeline({ evaluations }: { evaluations: Evaluation[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const sorted = [...evaluations].sort(
    (a, b) => new Date(a.evaluated_at).getTime() - new Date(b.evaluated_at).getTime()
  );

  const featureIds = [...new Set(sorted.map((e) => e.feature_id))];
  const laneMap = new Map<string, number>();
  featureIds.forEach((fid, i) => laneMap.set(fid, FIRST_LANE + i * LANE_GAP));

  const nodes: ProcessedNode[] = sorted.map((ev, i) => ({
    eval: ev,
    x: LEFT_PAD + i * X_STEP,
    laneY: laneMap.get(ev.feature_id) ?? FIRST_LANE,
    color: decisionColor[ev.decision],
    glow: decisionGlow[ev.decision],
  }));

  const svgWidth = LEFT_PAD + (nodes.length - 1) * X_STEP + RIGHT_PAD;
  const maxLaneY = FIRST_LANE + (featureIds.length - 1) * LANE_GAP;
  const svgHeight = maxLaneY + 40;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, []);

  const handleHover = useCallback((i: number | null, e?: React.MouseEvent) => {
    setHovered(i);
    if (i !== null && e && wrapperRef.current) {
      const wrapperRect = wrapperRef.current.getBoundingClientRect();
      const circleRect = (e.target as SVGCircleElement).getBoundingClientRect();
      setTooltipPos({
        x: circleRect.left + circleRect.width / 2 - wrapperRect.left,
        y: circleRect.top - wrapperRect.top,
      });
    } else {
      setTooltipPos(null);
    }
  }, []);

  if (nodes.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border-light dark:border-border-dark p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[12px] font-medium text-text-light-primary dark:text-text-primary">
            PR evaluation timeline defaults
          </p>
          <p className="text-[11px] text-text-light-muted dark:text-text-muted">
            Connect your codebase to get started
          </p>
        </div>
        <div className="flex items-center gap-3">
          {DEFAULT_TIMELINE_POINTS.map((point) => (
            <div key={point.label} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-text-light-muted dark:bg-text-muted" />
              <span className="text-[11px] text-text-light-muted dark:text-text-muted">
                {point.label} ({point.state})
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const cpOffset = X_STEP * 0.32;

  return (
    <div ref={wrapperRef} className="relative">
      {/* Tooltip — rendered outside scroll container, bottom-right of node */}
      {hovered !== null && nodes[hovered] && tooltipPos && (
        <div
          className="absolute z-50 pointer-events-none animate-scale-in origin-top-left"
          style={{
            left: tooltipPos.x + 12,
            top: tooltipPos.y + 12,
          }}
        >
          <TooltipCard node={nodes[hovered]} />
        </div>
      )}

      <div ref={scrollRef} className="overflow-x-auto pb-1">
        <div style={{ minWidth: svgWidth }}>
          <svg width={svgWidth} height={svgHeight} className="block" style={{ overflow: "visible" }}>
            {/* Main branch line */}
            <line
              x1={LEFT_PAD - 20}
              y1={MAIN_Y}
              x2={svgWidth - RIGHT_PAD + 20}
              y2={MAIN_Y}
              stroke="#555568"
              strokeWidth={2}
              strokeLinecap="round"
              opacity={0.5}
            />

            {nodes.map((node, i) => {
              const forkX = node.x - X_STEP * 0.38;
              const mergeX = node.x + X_STEP * 0.38;
              const isHovered = hovered === i;

              return (
                <g key={i} opacity={hovered !== null && !isHovered ? 0.35 : 1} className="transition-opacity duration-150">
                  <path
                    d={`M ${forkX},${MAIN_Y} C ${forkX + cpOffset},${MAIN_Y} ${node.x - cpOffset},${node.laneY} ${node.x},${node.laneY}`}
                    fill="none"
                    stroke={node.color}
                    strokeWidth={2}
                    strokeLinecap="round"
                    opacity={0.6}
                  />
                  <path
                    d={`M ${node.x},${node.laneY} C ${node.x + cpOffset},${node.laneY} ${mergeX - cpOffset},${MAIN_Y} ${mergeX},${MAIN_Y}`}
                    fill="none"
                    stroke={node.color}
                    strokeWidth={2}
                    strokeLinecap="round"
                    opacity={0.6}
                  />

                  <circle cx={forkX} cy={MAIN_Y} r={MAIN_DOT_R} fill={node.color} opacity={0.7} />
                  <circle cx={mergeX} cy={MAIN_Y} r={MAIN_DOT_R} fill={node.color} opacity={0.7} />

                  <circle
                    cx={node.x}
                    cy={node.laneY}
                    r={isHovered ? NODE_R + 10 : NODE_R + 6}
                    fill={node.glow}
                    className="transition-all duration-150"
                  />
                  <circle
                    cx={node.x}
                    cy={node.laneY}
                    r={isHovered ? NODE_R + 1 : NODE_R}
                    fill={node.color}
                    stroke={isHovered ? "#F5F5F7" : "transparent"}
                    strokeWidth={2}
                    className="cursor-pointer transition-all duration-150"
                    onMouseEnter={(e) => handleHover(i, e)}
                    onMouseLeave={() => handleHover(null)}
                  />

                  <text
                    x={node.x + NODE_R + 6}
                    y={node.laneY + 4}
                    className="fill-text-light-muted dark:fill-text-muted"
                    style={{ fontSize: 9, fontFamily: "ui-monospace, monospace" }}
                  >
                    {node.eval.pr_number ? `#${node.eval.pr_number}` : truncateSha(node.eval.commit_sha)}
                  </text>
                </g>
              );
            })}

            {nodes.map((node, i) => (
              <text
                key={`date-${i}`}
                x={node.x}
                y={svgHeight - 4}
                textAnchor="middle"
                className="fill-text-light-muted dark:fill-text-muted"
                style={{ fontSize: 9 }}
              >
                {new Date(node.eval.evaluated_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </text>
            ))}
          </svg>
        </div>
      </div>

      {/* Feature lane legend */}
      <div className="flex items-center gap-4 mt-2 px-1 flex-wrap">
        {featureIds.map((fid) => (
          <span key={fid} className="flex items-center gap-1.5 text-[10px] text-text-light-muted dark:text-text-muted">
            <span className="w-3 h-[2px] rounded-full bg-text-muted/40" />
            {fid}
          </span>
        ))}
      </div>
    </div>
  );
}

function TooltipCard({ node }: { node: ProcessedNode }) {
  const ev = node.eval;
  const date = new Date(ev.evaluated_at).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="rounded-xl border border-border-light dark:border-border-dark bg-bg-light-surface dark:bg-bg-elevated p-3 shadow-xl text-[11px] space-y-1.5 min-w-[180px]">
      <div className="flex items-center justify-between gap-3">
        <span className="font-semibold text-text-light-primary dark:text-text-primary">{ev.feature_id}</span>
        <span
          className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide"
          style={{ color: node.color, backgroundColor: node.glow }}
        >
          {decisionLabel[ev.decision]}
        </span>
      </div>
      <p className="text-text-light-muted dark:text-text-muted">{date}</p>
      <div className="flex items-center justify-between pt-1 border-t border-border-light dark:border-border-dark">
        <span className="text-text-light-muted dark:text-text-muted">Risk</span>
        <span className="font-bold tabular-nums" style={{ color: node.color }}>{ev.risk_score}</span>
      </div>
      {ev.pr_number && (
        <div className="flex items-center justify-between">
          <span className="text-text-light-muted dark:text-text-muted">PR</span>
          <span className="font-semibold text-accent dark:text-accent-secondary">#{ev.pr_number}</span>
        </div>
      )}
      {(ev.lines_added !== undefined || ev.lines_deleted !== undefined) && (
        <div className="flex items-center gap-3 pt-1 border-t border-border-light dark:border-border-dark">
          <span className="text-status-pass font-semibold tabular-nums">+{ev.lines_added ?? 0}</span>
          <span className="text-status-fail font-semibold tabular-nums">-{ev.lines_deleted ?? 0}</span>
        </div>
      )}
    </div>
  );
}
