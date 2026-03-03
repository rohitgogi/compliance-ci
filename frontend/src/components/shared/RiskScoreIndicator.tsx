import { riskScoreColor } from "@/lib/utils";

interface RiskScoreIndicatorProps {
  score: number;
  size?: "sm" | "md" | "lg";
}

export default function RiskScoreIndicator({ score, size = "md" }: RiskScoreIndicatorProps) {
  const sizeClasses = {
    sm: "text-sm",
    md: "text-lg font-semibold",
    lg: "text-2xl font-bold",
  };

  const barWidth = Math.min(score, 100);
  const barColor =
    score <= 30 ? "bg-status-pass" : score <= 69 ? "bg-status-review" : "bg-status-fail";

  return (
    <div className="flex items-center gap-3">
      <span className={`${sizeClasses[size]} ${riskScoreColor(score)} tabular-nums`}>
        {score}
      </span>
      <div className="flex flex-col gap-1">
        <span className="text-[10px] text-text-light-muted dark:text-text-muted uppercase tracking-wider font-medium">
          Risk
        </span>
        <div className="w-16 h-1 rounded-full bg-border-light dark:bg-white/6 overflow-hidden">
          <div
            className={`h-full rounded-full ${barColor} transition-all duration-500`}
            style={{ width: `${barWidth}%` }}
          />
        </div>
      </div>
    </div>
  );
}
