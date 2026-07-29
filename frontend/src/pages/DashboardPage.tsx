import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Activity, ArrowUpRight, Bot, ChartNoAxesCombined, Clock3, RefreshCw, ShieldCheck, TicketCheck, TriangleAlert, type LucideIcon } from "lucide-react";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import StatCard from "../components/StatCard";
import { api, type AuditRecord, type AuditStats } from "../lib/api";
import { TokenUsageSection } from "./TokenUsagePage";

const COLORS = ["#4f7df3", "#8b6df6", "#21b39b", "#f59e0b", "#f26d85"];

export default function DashboardPage() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true); setError("");
    Promise.all([api.getAuditStats(30), api.getAuditRecords({ limit: "12" })])
      .then(([statsData, recordsData]) => { setStats(statsData); setRecords(recordsData.records || []); })
      .catch(() => setError("暂时无法读取运行数据，请检查服务连接后重试。"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const skillData = useMemo(() => Object.entries(stats?.by_skill || {}).map(([name, value]) => ({ name: displaySkill(name), value })), [stats]);
  const trendData = useMemo(() => {
    const days: Record<string, number> = {};
    records.forEach((record) => { const day = (record.timestamp || "").slice(5, 10) || "未知"; days[day] = (days[day] || 0) + 1; });
    return Object.entries(days).map(([day, calls]) => ({ day, calls })).reverse();
  }, [records]);
  const totalCalls = stats?.total_calls || 0;
  const errors = stats?.errors || 0;

  return <div className="h-dvh overflow-y-auto"><div className="mx-auto max-w-7xl px-5 py-7 sm:px-8 lg:px-10"><PageTitle eyebrow="OPERATIONS & USAGE" title="运营与用量" description="集中查看 Agent 运行健康度、调用趋势与 Token 消耗。" action={<button onClick={load} disabled={loading} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"><RefreshCw size={14} className={loading ? "animate-spin" : ""} />刷新数据</button>} />
    {error && <div className="mb-5 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700"><TriangleAlert size={16} />{error}</div>}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard title="总调用量" value={number(totalCalls)} subtitle="近 30 天累计请求" icon={Activity} tone="blue" /><StatCard title="活跃处理能力" value={String(skillData.length)} subtitle="参与处理请求的 Agent / Skill" icon={Bot} tone="violet" /><StatCard title="平均响应时间" value={`${((stats?.avg_duration_ms || 0) / 1000).toFixed(1)}s`} subtitle="接口端到端平均耗时" icon={Clock3} tone="amber" /><StatCard title="任务成功率" value={totalCalls ? `${(((totalCalls - errors) / totalCalls) * 100).toFixed(1)}%` : "—"} subtitle={errors ? `${errors} 次请求需要关注` : "运行稳定"} icon={ShieldCheck} tone="green" /></div>
    <div className="mt-6 grid gap-5 xl:grid-cols-[1.25fr_.75fr]"><section className="panel p-5 sm:p-6"><SectionHeading icon={ChartNoAxesCombined} title="调用趋势" description="基于最近审计记录的调用分布" /><div className="mt-5 h-[250px]">{loading ? <ChartSkeleton /> : trendData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={trendData} barSize={28}><XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#94a3b8" }} dy={8} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#94a3b8" }} width={28} /><Tooltip cursor={{ fill: "#f1f5f9" }} contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", boxShadow: "0 8px 24px rgba(15,23,42,.08)", fontSize: 12 }} /><Bar dataKey="calls" name="调用次数" fill="#4f7df3" radius={[7, 7, 2, 2]} /></BarChart></ResponsiveContainer> : <EmptyChart label="还没有调用趋势数据" />}</div></section>
      <section className="panel p-5 sm:p-6"><SectionHeading icon={Bot} title="Agent 分布" description="近 30 天按处理能力统计" /><div className="mt-3 flex h-[266px] items-center">{loading ? <ChartSkeleton /> : skillData.length ? <><div className="h-full w-[58%]"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={skillData} dataKey="value" nameKey="name" innerRadius={52} outerRadius={78} paddingAngle={4}>{skillData.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}</Pie><Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", fontSize: 12 }} /></PieChart></ResponsiveContainer></div><div className="min-w-0 flex-1 space-y-3">{skillData.slice(0, 4).map((skill, index) => <div key={skill.name} className="flex items-center gap-2 text-xs"><span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} /><span className="truncate text-slate-500">{skill.name}</span><span className="ml-auto font-medium text-slate-700">{skill.value}</span></div>)}</div></> : <EmptyChart label="暂无 Agent 调用记录" />}</div></section></div>
    <section className="panel mt-6 overflow-hidden"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-5 sm:px-6"><div><h2 className="text-sm font-semibold text-slate-800">近期活动</h2><p className="mt-1 text-xs text-slate-400">最近 12 次模型调用的运行状态</p></div><span className="hidden items-center gap-1 text-xs font-medium text-blue-600 sm:flex">查看完整审计 <ArrowUpRight size={14} /></span></div>{loading ? <div className="p-6"><div className="h-12 animate-pulse rounded-lg bg-slate-100" /><div className="mt-3 h-12 animate-pulse rounded-lg bg-slate-100" /></div> : records.length ? <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-xs"><thead className="bg-slate-50/70 text-slate-400"><tr><th className="px-6 py-3 font-medium">时间</th><th className="px-4 py-3 font-medium">处理能力</th><th className="px-4 py-3 font-medium">耗时</th><th className="px-6 py-3 text-right font-medium">状态</th></tr></thead><tbody>{records.map((record) => <tr key={record.id} className="border-t border-slate-100 transition hover:bg-slate-50/60"><td className="px-6 py-4 text-slate-500">{formatTime(record.timestamp)}</td><td className="px-4 py-4"><span className="rounded-md bg-blue-50 px-2 py-1 font-medium text-blue-700">{displaySkill(record.skill_used || record.agent_type)}</span></td><td className="px-4 py-4 text-slate-500">{((record.duration_ms || 0) / 1000).toFixed(1)}s</td><td className="px-6 py-4 text-right">{record.error ? <span className="inline-flex items-center gap-1 text-rose-600"><TriangleAlert size={13} />异常</span> : <span className="inline-flex items-center gap-1 text-emerald-600"><TicketCheck size={13} />完成</span>}</td></tr>)}</tbody></table></div> : <div className="py-12 text-center text-sm text-slate-400">还没有可展示的调用记录</div>}</section>
    <TokenUsageSection />
  </div></div>;
}

export function PageTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) { return <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-[10px] font-semibold tracking-[.16em] text-blue-600">{eyebrow}</p><h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-800">{title}</h1><p className="mt-2 text-sm text-slate-500">{description}</p></div>{action}</div>; }
function SectionHeading({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description: string }) { return <div className="flex items-start gap-2.5"><span className="mt-0.5 rounded-lg bg-blue-50 p-1.5 text-blue-600"><Icon size={16} /></span><div><h2 className="text-sm font-semibold text-slate-800">{title}</h2><p className="mt-1 text-xs text-slate-400">{description}</p></div></div>; }
function ChartSkeleton() { return <div className="flex h-full items-end gap-3 px-4 pb-5"><span className="h-[35%] flex-1 animate-pulse rounded-t-lg bg-slate-100" /><span className="h-[62%] flex-1 animate-pulse rounded-t-lg bg-slate-100" /><span className="h-[45%] flex-1 animate-pulse rounded-t-lg bg-slate-100" /><span className="h-[78%] flex-1 animate-pulse rounded-t-lg bg-slate-100" /></div>; }
function EmptyChart({ label }: { label: string }) { return <div className="flex h-full w-full items-center justify-center text-sm text-slate-400">{label}</div>; }
function number(value: number) { return value.toLocaleString("zh-CN"); }
function displaySkill(name: string) { return name.replace("skill:", "").replace("_", " ") || "通用助手"; }
function formatTime(value: string) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value.slice(0, 16) : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
