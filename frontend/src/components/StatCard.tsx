import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon?: LucideIcon;
  tone?: "blue" | "violet" | "amber" | "green";
}

const tones = {
  blue: "bg-blue-50 text-blue-600",
  violet: "bg-violet-50 text-violet-600",
  amber: "bg-amber-50 text-amber-600",
  green: "bg-emerald-50 text-emerald-600",
};

export default function StatCard({ title, value, subtitle, icon: Icon, tone = "blue" }: StatCardProps) {
  return (
    <div className="panel p-5 transition duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-200/50">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[13px] font-medium text-slate-500">{title}</p>
          <p className="mt-2 text-[28px] font-semibold tracking-tight text-slate-800">{value}</p>
        </div>
        {Icon && <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${tones[tone]}`}><Icon size={20} /></span>}
      </div>
      {subtitle && <p className="mt-3 text-xs text-slate-400">{subtitle}</p>}
    </div>
  );
}
