import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import StatCard from "../components/StatCard";
import type { AuditStats, AuditRecord } from "../lib/api";

const COLORS = ["#2563eb", "#7c3aed", "#06b6d4", "#f59e0b", "#ef4444"];

export default function DashboardPage() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [records, setRecords] = useState<AuditRecord[]>([]);

  useEffect(() => {
    fetch("/audit/stats?days=30").then(r => r.json()).then(setStats).catch(() => {});
    fetch("/audit?limit=20").then(r => r.json()).then(d => setRecords(d.records || [])).catch(() => {});
  }, []);

  if (!stats) return <div className="p-8 text-gray-400">加载中...</div>;

  const skillData = Object.entries(stats.by_skill || {}).map(([name, value]) => ({ name, value }));
  const totalCalls = stats.total_calls || 0;
  const totalTokens = stats.total_tokens || 0;

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h2 className="text-lg font-semibold">运营总览</h2>

      <div className="grid grid-cols-4 gap-4">
        <StatCard title="总调用量" value={totalCalls.toLocaleString()} />
        <StatCard title="总 Token" value={(totalTokens / 1000).toFixed(1) + "K"} />
        <StatCard title="平均耗时" value={(stats.avg_duration_ms / 1000).toFixed(1) + "s"} />
        <StatCard title="错误率" value={totalCalls > 0 ? ((stats.error_count || 0) / totalCalls * 100).toFixed(1) + "%" : "0%"} color={stats.error_count > 0 ? "text-red-500" : "text-green-500"} />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-medium text-gray-600 mb-4">Skill 调用分布</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={skillData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                {skillData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-medium text-gray-600 mb-4">调用量趋势（最近7天）</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={[{ day: "待统计", calls: totalCalls }]}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="day" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="calls" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-medium text-gray-600 mb-4">最近调用记录</h3>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-gray-400 border-b"><th className="pb-2">时间</th><th className="pb-2">Skill</th><th className="pb-2">Token</th><th className="pb-2">耗时</th><th className="pb-2">状态</th></tr></thead>
          <tbody>
            {records.slice(0, 10).map((r, i) => (
              <tr key={i} className="border-b border-gray-50">
                <td className="py-2 text-gray-500">{r.created_at?.slice(11, 19) || "-"}</td>
                <td className="py-2">{r.skill_used || r.agent_type}</td>
                <td className="py-2 text-gray-500">{r.tokens_total?.toLocaleString()}</td>
                <td className="py-2 text-gray-500">{(r.duration_ms / 1000).toFixed(1)}s</td>
                <td className="py-2">{r.error ? <span className="text-red-500">失败</span> : <span className="text-green-500">成功</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
