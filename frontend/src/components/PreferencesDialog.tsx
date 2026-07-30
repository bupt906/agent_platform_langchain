import { useEffect, useState } from "react";
import { Check, CircleHelp, Monitor, Moon, RotateCcw, Save, Sun, X } from "lucide-react";
import { DEFAULT_PREFERENCES, type Preferences, type ThemePreference } from "../lib/preferences";

interface PreferencesDialogProps {
  open: boolean;
  preferences: Preferences;
  onClose: () => void;
  onSave: (preferences: Preferences) => Promise<void>;
  onReset: () => Promise<void>;
}

const themes: { value: ThemePreference; label: string; description: string; icon: typeof Sun }[] = [
  { value: "light", label: "明亮", description: "始终使用明亮界面", icon: Sun },
  { value: "dark", label: "深色", description: "降低暗光环境下的视觉疲劳", icon: Moon },
  { value: "system", label: "跟随系统", description: "自动同步设备主题", icon: Monitor },
];

export default function PreferencesDialog({ open, preferences, onClose, onSave, onReset }: PreferencesDialogProps) {
  const [draft, setDraft] = useState<Preferences>(preferences);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { if (open) setDraft(preferences); }, [open, preferences]);
  if (!open) return null;

  const save = async () => {
    setSaving(true); setError("");
    try {
      await onSave({ ...draft, defaultModel: draft.defaultModel.trim(), apiBaseUrl: normalizeBaseUrl(draft.apiBaseUrl) });
      onClose();
    } catch {
      setError("设置保存失败，请检查当前服务连接后重试。");
    } finally {
      setSaving(false);
    }
  };
  const reset = async () => {
    setSaving(true); setError("");
    try {
      await onReset();
      setDraft(DEFAULT_PREFERENCES);
    } catch {
      setError("恢复默认失败，请检查当前服务连接后重试。");
    } finally {
      setSaving(false);
    }
  };

  return <div className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/40 p-0 backdrop-blur-sm sm:items-center sm:p-5" role="dialog" aria-modal="true" aria-labelledby="preferences-title">
    <div className="w-full max-w-xl overflow-hidden rounded-t-3xl bg-white shadow-2xl shadow-slate-950/25 sm:rounded-3xl slide-up">
      <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4 sm:px-6"><div><h2 id="preferences-title" className="text-base font-semibold text-slate-800">偏好设置</h2><p className="mt-1 text-xs text-slate-400">设置仅保存在当前浏览器。</p></div><button onClick={onClose} className="rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600" aria-label="关闭设置"><X size={18} /></button></header>
      <div className="max-h-[70vh] space-y-7 overflow-y-auto px-5 py-6 sm:px-6">
        <section><div><h3 className="text-sm font-semibold text-slate-700">界面主题</h3><p className="mt-1 text-xs text-slate-400">选择你偏好的工作台显示方式。</p></div><div className="mt-3 grid gap-2 sm:grid-cols-3">{themes.map(({ value, label, description, icon: Icon }) => <button key={value} onClick={() => setDraft({ ...draft, theme: value })} className={`relative rounded-xl border p-3 text-left transition ${draft.theme === value ? "border-blue-400 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"}`}><Icon size={17} className={draft.theme === value ? "text-blue-600" : "text-slate-400"} /><p className="mt-3 text-xs font-semibold text-slate-700">{label}</p><p className="mt-1 text-[11px] leading-4 text-slate-400">{description}</p>{draft.theme === value && <Check size={13} className="absolute right-2.5 top-2.5 text-blue-600" />}</button>)}</div></section>
        <section className="border-t border-slate-100 pt-6"><h3 className="text-sm font-semibold text-slate-700">对话默认值</h3><p className="mt-1 text-xs text-slate-400">Agent 和 Skill 均由每次对话单独选择；留空时由后端识别意图。</p><label className="mt-4 block"><span className="flex items-center gap-1 text-xs font-medium text-slate-600">默认模型 ID <span title="格式为 provider:model，例如 deepseek:deepseek-chat"><CircleHelp size={12} className="text-slate-400" /></span></span><input value={draft.defaultModel} onChange={(event) => setDraft({ ...draft, defaultModel: event.target.value })} placeholder="使用后端默认模型" className="focus-ring mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 placeholder:text-slate-400" /></label></section>
        <section className="border-t border-slate-100 pt-6"><h3 className="text-sm font-semibold text-slate-700">服务连接</h3><p className="mt-1 text-xs leading-5 text-slate-400">开发环境留空即可使用 Vite 代理；部署到独立前端时，可填写后端地址。</p><label className="mt-4 block"><span className="text-xs font-medium text-slate-600">API 基础地址</span><input value={draft.apiBaseUrl} onChange={(event) => setDraft({ ...draft, apiBaseUrl: event.target.value })} placeholder="例如 http://localhost:8000" className="focus-ring mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 placeholder:text-slate-400" /></label></section>
      </div>
      <footer className="border-t border-slate-100 px-5 py-4 sm:px-6">{error && <p className="mb-3 text-xs text-rose-600">{error}</p>}<div className="flex items-center justify-between"><button onClick={reset} disabled={saving} className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 transition hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50"><RotateCcw size={14} />恢复默认</button><div className="flex gap-2"><button onClick={onClose} disabled={saving} className="rounded-xl px-3 py-2 text-xs font-medium text-slate-500 transition hover:bg-slate-100 disabled:opacity-50">取消</button><button onClick={save} disabled={saving} className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-3.5 py-2 text-xs font-medium text-white shadow-md shadow-blue-200 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"><Save size={14} />{saving ? "保存中…" : "保存设置"}</button></div></div></footer>
    </div>
  </div>;
}

function normalizeBaseUrl(value: string) {
  return value.trim().replace(/\/+$/, "");
}
