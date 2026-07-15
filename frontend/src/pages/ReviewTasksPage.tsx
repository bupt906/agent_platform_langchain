import { useState } from "react";
import { ChevronDown, ChevronRight, AlertTriangle, CheckCircle, XCircle, Clock } from "lucide-react";
import type { ReviewResult } from "../lib/api";

interface TaskSummary { task_id: number; status: string }

export default function ReviewTasksPage() {
  const [taskId, setTaskId] = useState("");
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [results, setResults] = useState<ReviewResult[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);

  const loadResults = async (tid: number) => {
    setLoading(true);
    try {
      const r = await fetch(`/api/callback/batch/${tid}`);
      const data = await r.json();
      setResults(data.data?.results || []);
      setExpanded(true);
    } catch { setResults([]); }
    setLoading(false);
  };

  // mock: list recent tasks (callback stores in-memory, would need API)
  const handleSearch = async () => {
    const tid = parseInt(taskId);
    if (isNaN(tid)) return;
    const r = await fetch(`/api/callback/task/status/${tid}`);
    const d = await r.json();
    if (d.code === 200 && d.data) {
      setTasks([{ task_id: tid, status: d.data.status }]);
      loadResults(tid);
    }
  };

  const statusIcon = (s: string) => {
    switch (s) {
      case "1": return <Clock size={14} className="text-amber-500" />;
      case "2": return <CheckCircle size={14} className="text-green-500" />;
      case "3": return <XCircle size={14} className="text-red-500" />;
      default: return null;
    }
  };
  const statusText = (s: string) => ({ "1": "审阅中", "2": "审阅完毕", "3": "失败" })[s] || s;

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h2 className="text-lg font-semibold">审阅任务</h2>

      <div className="flex gap-2">
        <input className="border rounded-lg px-3 py-2 text-sm w-40" placeholder="输入任务 ID" value={taskId} onChange={e => setTaskId(e.target.value)} onKeyDown={e => e.key === "Enter" && handleSearch()} />
        <button onClick={handleSearch} className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-600">查询</button>
      </div>

      {tasks.map(t => (
        <div key={t.task_id} className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            {statusIcon(t.status)}
            <span className="font-medium">任务 #{t.task_id}</span>
            <span className="text-sm text-gray-500">{statusText(t.status)}</span>
            <button onClick={() => loadResults(t.task_id)} className="ml-auto flex items-center gap-1 text-sm text-blue-500">
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />} 详情
            </button>
          </div>

          {loading && <div className="text-sm text-gray-400 mt-2">加载中...</div>}

          {expanded && results.length > 0 && (
            <div className="mt-4 space-y-2 max-h-96 overflow-y-auto">
              {results.map((r, i) => (
                <div key={i} className={`p-3 rounded-lg text-sm ${r.has_issue === "是" ? "bg-red-50 border border-red-100" : "bg-green-50 border border-green-100"}`}>
                  <div className="flex items-start gap-2">
                    {r.has_issue === "是" ? <AlertTriangle size={14} className="text-red-500 mt-0.5 shrink-0" /> : <CheckCircle size={14} className="text-green-500 mt-0.5 shrink-0" />}
                    <div>
                      <p className="text-gray-800">{r.reviewed_sentence}</p>
                      {r.has_issue === "是" && r.content && (
                        <div className="mt-2 space-y-1 text-xs text-gray-600">
                          {Object.entries(r.content as Record<string, unknown>).map(([k, v]) => (
                            <div key={k}><span className="font-medium">{k}:</span> {typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {expanded && results.length === 0 && !loading && (
            <div className="text-sm text-gray-400 mt-2">暂无审阅结果</div>
          )}
        </div>
      ))}

      {tasks.length === 0 && (
        <div className="text-gray-400 text-sm">输入任务 ID 查询审阅结果</div>
      )}
    </div>
  );
}
