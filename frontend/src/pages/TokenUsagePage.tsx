import { useEffect, useState } from "react";
import { api, type AuditRecord } from "../lib/api";

export default function TokenUsagePage() {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [skillFilter, setSkillFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const params: Record<string, string> = { limit: "100" };
    if (skillFilter) params.skill_used = skillFilter;

    api.getAuditRecords(params)
      .then(d => {
        if (!cancelled) setRecords(d.records || []);
      })
      .catch(e => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [skillFilter]);

  const totalTokens = records.reduce((s, r) => s + (r.tokens_total || 0), 0);

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">用量分析</h2>
        <select className="border rounded-lg px-3 py-1.5 text-sm" value={skillFilter} onChange={e => setSkillFilter(e.target.value)}>
          <option value="">全部 Skill</option>
          <option value="document_review">document_review</option>
          <option value="knowledge-graph-extraction">knowledge-graph-extraction</option>
        </select>
      </div>

      {error && <div className="text-sm text-red-500">加载失败: {error}</div>}

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">总 Token 消耗</p>
          <p className="text-2xl font-bold text-blue-600">{(totalTokens / 1000).toFixed(1)}K</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">调用次数</p>
          <p className="text-2xl font-bold">{records.length}</p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-medium text-gray-600 mb-4">Token 消耗明细</h3>
        {loading ? (
          <div className="text-sm text-gray-400">加载中...</div>
        ) : records.length > 0 ? (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-gray-400 border-b"><th className="pb-2">时间</th><th className="pb-2">Session</th><th className="pb-2">Skill</th><th className="pb-2">Token</th><th className="pb-2">耗时</th></tr></thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-gray-50">
                  <td className="py-2 text-gray-500">{r.created_at?.slice(0, 19) || "-"}</td>
                  <td className="py-2 text-gray-500 font-mono text-xs">{r.session_id?.slice(0, 12) || "-"}</td>
                  <td className="py-2">{r.skill_used}</td>
                  <td className="py-2">{r.tokens_total?.toLocaleString()}</td>
                  <td className="py-2 text-gray-500">{(r.duration_ms / 1000).toFixed(1)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm text-gray-400 text-center py-4">暂无记录</div>
        )}
      </div>
    </div>
  );
}
