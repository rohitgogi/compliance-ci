"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface RiskBucket {
  bucket: string;
  count: number;
}

const bucketColors = ["#34D399", "#34D399", "#FBBF24", "#F87171", "#F87171"];

interface RiskDistributionChartProps {
  data: RiskBucket[];
}

export default function RiskDistributionChart({ data }: RiskDistributionChartProps) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis
          dataKey="bucket"
          tick={{ fontSize: 10, fill: "#555568" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "#555568" }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#141420",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "10px",
            fontSize: "11px",
            color: "#F5F5F7",
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
          }}
          cursor={{ fill: "rgba(139,92,246,0.05)" }}
          labelStyle={{ color: "#A0A0B8", fontSize: "10px" }}
        />
        <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={28}>
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={bucketColors[index]} fillOpacity={0.7} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
