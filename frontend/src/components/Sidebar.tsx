import { NavLink } from "react-router-dom";
import { MessageSquare, BarChart3, ClipboardList, Share2, Coins } from "lucide-react";

const links = [
  { to: "/", icon: MessageSquare, label: "对话" },
  { to: "/dashboard", icon: BarChart3, label: "总览" },
  { to: "/review-tasks", icon: ClipboardList, label: "审阅" },
  { to: "/graphs", icon: Share2, label: "图谱" },
  { to: "/tokens", icon: Coins, label: "用量" },
];

export default function Sidebar() {
  return (
    <aside className="w-14 bg-white border-r border-gray-200 flex flex-col items-center py-4 gap-2 shrink-0">
      <div className="text-lg font-bold text-blue-600 mb-4">A</div>
      {links.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            `p-2.5 rounded-lg transition-colors group relative ${
              isActive ? "bg-blue-50 text-blue-600" : "text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            }`
          }
        >
          <Icon size={20} />
          <span className="absolute left-14 bg-gray-800 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none z-50">
            {label}
          </span>
        </NavLink>
      ))}
    </aside>
  );
}
