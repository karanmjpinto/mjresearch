import { Routes, Route, Navigate } from "react-router-dom";
import { Dashboard } from "@/components/Dashboard";
import { ResearchReport } from "@/components/ResearchReport";
import PortfolioView from "@/components/PortfolioView";
import { ScreenersView } from "@/components/ScreenersView";
import { DEFAULT_SCREENER_ID } from "@/config/screeners";

export default function App() {
  return (
    <div className="min-h-screen bg-surface">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/research/:ticker?" element={<ResearchReport />} />
        <Route path="/portfolio" element={<PortfolioView />} />
        <Route path="/screeners" element={<Navigate to={`/screeners/${DEFAULT_SCREENER_ID}`} replace />} />
        <Route path="/screeners/:screenId" element={<ScreenersView />} />
      </Routes>
    </div>
  );
}
