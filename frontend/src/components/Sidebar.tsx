import { NavLink } from "react-router-dom";
import { BarChart3, Bot, ChevronLeft, ClipboardCheck, MessageSquareMore, Network, Settings } from "lucide-react";
import { useState } from "react";
import PreferencesDialog from "./PreferencesDialog";
import { usePreferences } from "../hooks/usePreferences";

const links = [
  { to: "/", icon: MessageSquareMore, label: "智能对话", hint: "与 Agent 协作" },
  { to: "/review-tasks", icon: ClipboardCheck, label: "文档审阅", hint: "审阅任务与结果" },
  { to: "/graphs", icon: Network, label: "知识图谱", hint: "抽取与可视化" },
  { to: "/dashboard", icon: BarChart3, label: "运营与用量", hint: "运行健康与 Token 消耗" },
];

export default function Sidebar() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { preferences, save, reset } = usePreferences();
  return (
    <><aside className="hidden w-[252px] shrink-0 flex-col bg-[#101827] px-3 py-4 text-slate-300 lg:flex">
      <div className="mb-8 flex items-center gap-3 px-3 pt-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-400 to-indigo-500 shadow-lg shadow-blue-950/40">
          <Bot size={23} className="text-white" strokeWidth={2.2} />
        </div>
        <div>
          <p className="text-[15px] font-semibold tracking-tight text-white">Agent Studio</p>
          <p className="mt-0.5 text-[11px] text-slate-500">智能体工作台</p>
        </div>
      </div>

      <p className="mb-2 px-3 text-[10px] font-semibold tracking-[.14em] text-slate-500">WORKSPACE</p>
      <nav className="space-y-1">
        {links.map(({ to, icon: Icon, label, hint }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all ${
              isActive ? "bg-blue-500/15 text-white shadow-sm ring-1 ring-inset ring-blue-400/15" : "text-slate-400 hover:bg-white/[.055] hover:text-slate-100"
            }`}
          >
            <Icon size={18} className="shrink-0" strokeWidth={isActivePath(to) ? 2.4 : 1.8} />
            <span className="text-sm font-medium">{label}</span>
            <span className="sr-only">{hint}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto space-y-3">
        <div className="rounded-xl border border-white/[.08] bg-white/[.035] p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-200"><span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" /></span>服务运行中</div>
          <p className="mt-1.5 text-[11px] leading-4 text-slate-500">Agent 与工具服务状态正常</p>
        </div>
        <button onClick={() => setSettingsOpen(true)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-slate-500 transition hover:bg-white/[.055] hover:text-slate-300">
          <Settings size={18} /> 偏好设置
          <ChevronLeft size={15} className="ml-auto" />
        </button>
      </div>
    </aside><PreferencesDialog open={settingsOpen} preferences={preferences} onClose={() => setSettingsOpen(false)} onSave={save} onReset={reset} /></>
  );
}

function isActivePath(to: string) {
  return window.location.pathname === to;
}
