import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { BarChart3, ClipboardCheck, MessageSquareMore, Network } from "lucide-react";
import Sidebar from "./components/Sidebar";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";
import ReviewTasksPage from "./pages/ReviewTasksPage";
import GraphViewerPage from "./pages/GraphViewerPage";
import { PreferencesProvider } from "./hooks/PreferencesProvider";

const mobileLinks = [
  { to: "/", icon: MessageSquareMore, label: "对话" },
  { to: "/review-tasks", icon: ClipboardCheck, label: "审阅" },
  { to: "/graphs", icon: Network, label: "图谱" },
  { to: "/dashboard", icon: BarChart3, label: "运营" },
];

export default function App() {
  return (
    <BrowserRouter>
      <PreferencesProvider><div className="app-surface flex min-h-dvh">
          <Sidebar />
          <main className="min-w-0 flex-1 overflow-hidden pb-16 lg:pb-0">
            <Routes>
              <Route path="/" element={<ChatPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/review-tasks" element={<ReviewTasksPage />} />
              <Route path="/graphs" element={<GraphViewerPage />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
          <nav className="fixed inset-x-0 bottom-0 z-50 flex h-16 items-center justify-around border-t border-slate-200 bg-white/95 px-2 backdrop-blur lg:hidden">
            {mobileLinks.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `flex min-w-12 flex-col items-center gap-1 rounded-lg px-2 py-1 text-[10px] ${isActive ? "text-blue-600" : "text-slate-400"}`}>
                <Icon size={19} strokeWidth={2} />{label}
              </NavLink>
            ))}
          </nav>
      </div></PreferencesProvider>
    </BrowserRouter>
  );
}

function NotFound() {
  return <div className="flex h-full min-h-[50vh] items-center justify-center"><div className="text-center"><p className="text-5xl font-semibold text-slate-200">404</p><p className="mt-3 text-sm text-slate-500">这个页面不存在</p></div></div>;
}
