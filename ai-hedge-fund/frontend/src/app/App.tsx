import { Routes, Route, Navigate } from "react-router-dom";
import { AutoResearchView } from "@/components/AutoResearchView";
import { BackendGate } from "@/components/BackendGate";
import { Dashboard } from "@/components/Dashboard";
import { DecideView } from "@/components/DecideView";
import { Landing } from "@/components/Landing";
import { OptimizeView } from "@/components/OptimizeView";
import { PlanView } from "@/components/PlanView";
import PortfolioView from "@/components/PortfolioView";
import { ResearchReport } from "@/components/ResearchReport";
import { ScreenersView } from "@/components/ScreenersView";
import { StageComingSoon } from "@/components/StageComingSoon";
import { SetupView } from "@/components/SetupView";
import { DEFAULT_SCREENER_ID } from "@/config/screeners";

/**
 * `/` is the landing page and makes no API calls, so the published static build
 * always renders something useful. Every other route needs the local backend
 * and sits behind BackendGate, which explains an unreachable API once instead
 * of letting a dozen panels fail separately and look broken.
 */
export default function App() {
  return (
    <div className="min-h-screen bg-surface">
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="*"
          element={
            <BackendGate>
              <AppRoutes />
            </BackendGate>
          }
        />
      </Routes>
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/plan/:ticker?" element={<PlanView />} />
      <Route path="/research/:ticker?" element={<ResearchReport />} />
      <Route path="/portfolio" element={<PortfolioView />} />
      <Route
        path="/screeners"
        element={<Navigate to={`/screeners/${DEFAULT_SCREENER_ID}`} replace />}
      />
      <Route path="/screeners/:screenId" element={<ScreenersView />} />
      <Route path="/optimize" element={<OptimizeView />} />
      <Route path="/lens/:ticker?" element={<StageComingSoon stage="lens" />} />
      <Route path="/value/:ticker?" element={<StageComingSoon stage="value" />} />
      <Route path="/decide/:ticker?" element={<DecideView />} />
      <Route path="/autoresearch" element={<AutoResearchView />} />
      <Route path="/setup" element={<SetupView />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
