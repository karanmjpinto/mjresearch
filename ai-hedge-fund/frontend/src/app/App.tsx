import { Routes, Route, Navigate } from "react-router-dom";
import { AutoResearchView } from "@/components/AutoResearchView";
import { BackendGate } from "@/components/BackendGate";
import { DeploymentLimits } from "@/components/DeploymentLimits";
import { Dashboard } from "@/components/Dashboard";
import { DocsView } from "@/components/DocsView";
import { DecideView } from "@/components/DecideView";
import { JoinView } from "@/components/JoinView";
import { Landing } from "@/components/Landing";
import { MemberGate } from "@/components/MemberGate";
import { OptimizeView } from "@/components/OptimizeView";
import { AnalysisView } from "@/components/AnalysisView";
import { ValueRiskView } from "@/components/ValueRiskView";
import { YourLensView } from "@/components/YourLensView";
import PortfolioView from "@/components/PortfolioView";
import { ResearchReport } from "@/components/ResearchReport";
import { ScreenersView } from "@/components/ScreenersView";
import { BreadthView } from "@/components/BreadthView";
import { ConstraintsView } from "@/components/ConstraintsView";
import { SetupView } from "@/components/SetupView";
import { DEFAULT_SCREENER_ID } from "@/config/screeners";

/**
 * `/` and `/docs` make no API calls, so the published static build always
 * renders something useful. Every other route needs the local backend and sits
 * behind BackendGate, which explains an unreachable API once instead of letting
 * a dozen panels fail separately and look broken.
 *
 * `/docs` is deliberately outside the gate: the reference section explains what
 * the app computes and what it merely writes, and that is exactly what someone
 * wants to read *before* deciding to run anything — including from the static
 * build, where there is no backend to reach at all.
 *
 * `/join` is outside both gates, and has to be: it is how a session is
 * obtained, so requiring one to reach it would be a closed loop. It sits
 * beside Landing rather than inside BackendGate because a visitor holding an
 * invite for a deployment whose API is briefly down should be told that by the
 * join screen's own failure, not sent to a page explaining that the app runs
 * on their machine.
 *
 * MemberGate is nested *inside* BackendGate, not beside it, because the two
 * answer different questions and the order matters. By the time MemberGate
 * runs, health has already replied, so a refusal can only mean "you are not a
 * member" — never "there is nothing here". Telling someone to clone a
 * repository when the truth is they have not been let in is the worse mistake
 * of the two.
 */
export default function App() {
  return (
    <div className="min-h-screen bg-surface">
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/docs" element={<DocsView />} />
        <Route path="/join" element={<JoinView />} />
        <Route
          path="*"
          element={
            <BackendGate>
              <MemberGate>
                {/* Above the routes rather than inside each one: the limits are
                    a property of the deployment, not of the screen you happen
                    to be on, and it renders nothing when nothing is limited. */}
                <DeploymentLimits />
                <AppRoutes />
              </MemberGate>
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
      <Route path="/plan/:ticker?" element={<AnalysisView />} />
      <Route path="/research/:ticker?" element={<ResearchReport />} />
      <Route path="/portfolio" element={<PortfolioView />} />
      <Route
        path="/screeners"
        element={<Navigate to={`/screeners/${DEFAULT_SCREENER_ID}`} replace />}
      />
      <Route path="/screeners/:screenId" element={<ScreenersView />} />
      <Route path="/optimize" element={<OptimizeView />} />
      <Route path="/constraints" element={<ConstraintsView />} />
      <Route path="/breadth" element={<BreadthView />} />
      <Route path="/lens/:ticker?" element={<YourLensView />} />
      <Route path="/value/:ticker?" element={<ValueRiskView />} />
      <Route path="/decide/:ticker?" element={<DecideView />} />
      <Route path="/autoresearch" element={<AutoResearchView />} />
      <Route path="/setup" element={<SetupView />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
