import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3, FileSearch, LoaderCircle, Search, XCircle } from "lucide-react";
import { PageTitle } from "./DashboardPage";
import { api, type ReviewResult } from "../lib/api";

interface TaskSummary { taskId: number; status: string; }

const statusMeta: Record<string, { label: string; description: string; className: string; icon: typeof Clock3 }> = {
  "520": { label: "审阅中", description: "系统正在解析文档并逐句核验", className: "bg-amber-50 text-amber-700 ring-amber-200", icon: Clock3 },
  "530": { label: "审阅完成", description: "审阅结果已生成，可查看问题详情", className: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: CheckCircle2 },
  "777": { label: "执行失败", description: "任务未能完成，请检查文件或服务状态", className: "bg-rose-50 text-rose-700 ring-rose-200", icon: XCircle },
};

export default function ReviewTasksPage() {
  const [taskInput, setTaskInput] = useState("");
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [results, setResults] = useState<ReviewResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [error, setError] = useState("");

  const lookupTask = async () => {
    const id = Number(taskInput.trim());
    if (!Number.isInteger(id) || id < 0) { setError("请输入有效的数字任务 ID。"); return; }
    setLoading(true); setError(""); setTask(null); setResults([]);
    try {
      const status = await api.getTaskStatus(id);
      setTask({ taskId: id, status: status.data?.status || "unknown" });
      try {
        const detail = await api.getReviewResults(id);
        setResults(detail.data?.results || []);
      } catch { setError("任务状态已获取，但审阅结果暂不可用。任务仍可能在处理中。"); }
    } catch { setError("未找到该任务，或暂时无法连接到审阅服务。"); }
    finally { setLoading(false); }
  };

  const meta = task ? statusMeta[task.status] || { label: task.status || "未知状态", description: "等待任务状态同步", className: "bg-slate-100 text-slate-600 ring-slate-200", icon: Clock3 } : null;
  const issues = results.filter((result) => result.has_issue === "是");

  return <div className="h-dvh overflow-y-auto"><div className="mx-auto max-w-6xl px-5 py-7 sm:px-8 lg:px-10"><PageTitle eyebrow="DOCUMENT REVIEW" title="文档审阅" description="查询异步审阅任务，查看基于知识库的逐句核验结果。" />
    <section className="panel overflow-hidden"><div className="grid lg:grid-cols-[1.1fr_.9fr]"><div className="p-6 sm:p-7"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-600"><FileSearch size={21} /></div><h2 className="mt-5 text-lg font-semibold text-slate-800">查询审阅任务</h2><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">输入提交文档时返回的任务 ID。我们会同步查询任务状态和已生成的审阅结果。</p><div className="mt-6 flex max-w-md gap-2"><input value={taskInput} onChange={(event) => setTaskInput(event.target.value)} onKeyDown={(event) => event.key === "Enter" && lookupTask()} inputMode="numeric" placeholder="例如 10086" className="focus-ring min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-700 placeholder:text-slate-400" /><button onClick={lookupTask} disabled={loading} className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-md shadow-blue-200 transition hover:bg-blue-700 disabled:opacity-60">{loading ? <LoaderCircle size={16} className="animate-spin" /> : <Search size={16} />}查询</button></div>{error && <p className="mt-3 text-xs leading-5 text-rose-600">{error}</p>}</div><div className="border-t border-slate-100 bg-slate-50/70 p-6 sm:p-7 lg:border-l lg:border-t-0"><p className="text-xs font-semibold text-slate-500">任务状态说明</p><div className="mt-4 space-y-3"><StatusHint icon={Clock3} title="审阅中（520）" description="正在进行知识库检索与逐句判定" tone="amber" /><StatusHint icon={CheckCircle2} title="审阅完成（530）" description="结果已提交，可以查看问题明细" tone="green" /><StatusHint icon={XCircle} title="执行失败（777）" description="文件、知识库或回调服务出现异常" tone="rose" /></div></div></div></section>
    {loading && <section className="panel mt-6 p-7"><div className="flex items-center gap-3 text-sm text-slate-500"><LoaderCircle size={18} className="animate-spin text-blue-500" />正在读取任务数据…</div></section>}
    {task && meta && <section className="panel mt-6 overflow-hidden fade-in"><div className="flex flex-col gap-5 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between sm:px-7"><div className="flex items-center gap-3"><div className={`flex h-10 w-10 items-center justify-center rounded-xl ${meta.className}`}><meta.icon size={19} /></div><div><p className="text-sm font-semibold text-slate-800">审阅任务 #{task.taskId}</p><p className="mt-1 text-xs text-slate-400">{meta.description}</p></div></div><span className={`inline-flex w-fit rounded-full px-3 py-1.5 text-xs font-medium ring-1 ring-inset ${meta.className}`}>{meta.label}</span></div>
      <div className="grid border-b border-slate-100 sm:grid-cols-3"><Summary label="已审句子" value={String(results.length)} /><Summary label="发现问题" value={String(issues.length)} danger={issues.length > 0} /><Summary label="合规通过" value={String(Math.max(results.length - issues.length, 0))} good /></div>
      <div className="p-5 sm:p-7"><button onClick={() => setExpanded(!expanded)} className="flex w-full items-center justify-between text-left"><span><span className="text-sm font-semibold text-slate-800">逐句审阅结果</span><span className="ml-2 text-xs text-slate-400">{results.length ? `${results.length} 条` : "暂无结果"}</span></span>{expanded ? <ChevronDown size={18} className="text-slate-400" /> : <ChevronRight size={18} className="text-slate-400" />}</button>{expanded && <ResultList results={results} />}</div>
    </section>}
  </div></div>;
}

function ResultList({ results }: { results: ReviewResult[] }) {
  if (!results.length) return <div className="mt-6 rounded-xl border border-dashed border-slate-200 py-10 text-center text-sm text-slate-400">尚未产生审阅明细；若任务仍在执行，请稍后刷新查询。</div>;
  return <div className="mt-5 space-y-3">{results.map((result) => <article key={result.sentence_index} className={`rounded-xl border p-4 ${result.has_issue === "是" ? "border-rose-100 bg-rose-50/40" : "border-emerald-100 bg-emerald-50/35"}`}><div className="flex items-start gap-3">{result.has_issue === "是" ? <AlertTriangle size={17} className="mt-0.5 shrink-0 text-rose-500" /> : <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-emerald-500" />}<div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="text-[11px] font-medium text-slate-400">第 {result.sentence_index + 1} 句</span><span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${result.has_issue === "是" ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}`}>{result.has_issue === "是" ? "发现问题" : "通过"}</span></div><p className="mt-2 text-sm leading-6 text-slate-700">{result.reviewed_sentence}</p>{result.has_issue === "是" && <ReviewDetail content={result.content} />}</div></div></article>)}</div>;
}

function ReviewDetail({ content }: { content: Record<string, unknown> }) { const entries = Object.entries(content || {}); if (!entries.length) return null; return <div className="mt-3 grid gap-2 rounded-lg border border-rose-100 bg-white/80 p-3 text-xs sm:grid-cols-2">{entries.map(([key, value]) => <div key={key} className="min-w-0"><span className="font-medium text-slate-500">{key}</span><p className="mt-1 break-words leading-5 text-slate-600">{typeof value === "object" ? JSON.stringify(value) : String(value)}</p></div>)}</div>; }
function StatusHint({ icon: Icon, title, description, tone }: { icon: typeof Clock3; title: string; description: string; tone: "amber" | "green" | "rose" }) { const color = tone === "amber" ? "bg-amber-100 text-amber-600" : tone === "green" ? "bg-emerald-100 text-emerald-600" : "bg-rose-100 text-rose-600"; return <div className="flex items-center gap-3"><span className={`flex h-8 w-8 items-center justify-center rounded-lg ${color}`}><Icon size={15} /></span><div><p className="text-xs font-medium text-slate-600">{title}</p><p className="mt-0.5 text-[11px] text-slate-400">{description}</p></div></div>; }
function Summary({ label, value, danger, good }: { label: string; value: string; danger?: boolean; good?: boolean }) { return <div className="border-b border-slate-100 px-5 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:px-7 sm:last:border-r-0"><p className="text-xs text-slate-400">{label}</p><p className={`mt-1 text-xl font-semibold ${danger ? "text-rose-600" : good ? "text-emerald-600" : "text-slate-700"}`}>{value}</p></div>; }
