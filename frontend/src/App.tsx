import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";
import ReviewTasksPage from "./pages/ReviewTasksPage";
import GraphViewerPage from "./pages/GraphViewerPage";
import TokenUsagePage from "./pages/TokenUsagePage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/review-tasks" element={<ReviewTasksPage />} />
            <Route path="/graphs" element={<GraphViewerPage />} />
            <Route path="/tokens" element={<TokenUsagePage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
