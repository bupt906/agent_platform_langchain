import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import StatCard from "../components/StatCard";
import { api, type AuditStats, type AuditRecord } from "../lib/api";

const COLORS = ["#2563eb", "#7c3aed", "#06b6d4", "#f59e0b", "#ef4444"];

export default function DashboardPage() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [statsData, recordsData] = await Promise.all([
          api.getAuditStats(30),
          api.getAuditRecords({ limit: "10" }),
        ]);
        if (!cancelled) {
          setStats(statsData);
          setRecords(recordsData.records || []);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  if (loading && !stats) return <div className="p-8 text-gray-400">加载中...</div>;
  if (error && !stats) return <div className="p-8 text-red-500">加载失败: {error} <button className="text-blue-500 underline ml-2" onClick={() => window.location.reload()}>重试</button></div>;
  if (!stats) return <div className="p-8 text-gray-400">暂无数据</div>;

  const skillData = Object.entries(stats.by_skill || {}).map(([name, value]) => ({ name, value }));
  const totalCalls = stats.total_calls || 0;
  const totalTokens = stats.total_tokens || 0;

  // 从审计记录中构建接近的每日统计（实际应使用专用趋势 API）
  const dailyMap: Record<string, number> = {};
  records.forEach(r => {
    const day = r.created_at?.slice(0, 10) || "未知";
    dailyMap[day] = (dailyMap[day] || 0) + 1;
  });
  const trendData = Object.entries(dailyMap)
    .map(([day, calls]) => ({ day, calls }))
    .sort((a, b) => a.day.localeCompare(b.day));

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
          {skillData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={skillData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                  {skillData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-gray-400 text-sm text-center py-20">暂无数据</div>
          )}
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-medium text-gray-600 mb-4">每日调用量</h3>
          {trendData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="calls" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-gray-400 text-sm text-center py-20">暂无数据</div>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-medium text-gray-600 mb-4">最近调用记录</h3>
        {records.length > 0 ? (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-gray-400 border-b"><th className="pb-2">时间</th><th className="pb-2">Skill</th><th className="pb-2">Token</th><th className="pb-2">耗时</th><th className="pb-2">状态</th></tr></thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-gray-50">
                  <td className="py-2 text-gray-500">{r.created_at?.slice(11, 19) || "-"}</td>
                  <td className="py-2">{r.skill_used || r.agent_type}</td>
                  <td className="py-2 text-gray-500">{r.tokens_total?.toLocaleString()}</td>
                  <td className="py-2 text-gray-500">{(r.duration_ms / 1000).toFixed(1)}s</td>
                  <td className="py-2">{r.error ? <span className="text-red-500">失败</span> : <span className="text-green-500">成功</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-gray-400 text-sm text-center py-4">暂无调用记录</div>
        )}
      </div>
    </div>
  );
}
