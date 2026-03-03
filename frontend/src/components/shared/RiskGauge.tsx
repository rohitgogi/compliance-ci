"use client";

import { riskScoreColor } from "@/lib/utils";

interface RiskGaugeProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  showLabel?: boolean;
}

export default function RiskGauge({
  score,
  size = 72,
  strokeWidth = 5,
  showLabel = true,
}: RiskGaugeProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const colorClass = riskScoreColor(score);

  const strokeColor =
    score <= 30 ? "#34D399" : score <= 69 ? "#FBBF24" : "#F87171";
  const trackColor = "rgba(139, 143, 181, 0.1)";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-lg font-bold tabular-nums leading-none ${colorClass}`}>
          {score}
        </span>
        {showLabel && (
          <span className="text-[9px] font-medium text-text-light-muted dark:text-text-muted uppercase tracking-wider mt-0.5">
            Risk
          </span>
        )}
      </div>
    </div>
  );
}
