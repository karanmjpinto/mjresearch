import { Suspense, lazy } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import clsx from "clsx";
import { BackendGate } from "@/components/BackendGate";
import { DeploymentLimits } from "@/components/DeploymentLimits";
import { JoinView } from "@/components/JoinView";
import { Landing } from "@/components/Landing";
import { MemberGate } from "@/components/MemberGate";
import { DEFAULT_SCREENER_ID } from "@/config/screeners";

/**
 * Landing, the two gates and JoinView are imported eagerly: they are the first
 * paint and the entry path, and a spinner on `/` would be a regression.
 *
 * Every screen below is a separate chunk, because statically importing all
 * nineteen put the whole app in one 1.36 MB file — recharts, lightweight-charts
 * and every panel downloaded and parsed before `/` could render, on a route
 * that the comment above says makes no API calls and needs none of it.
 * A visitor reading the landing page or the docs now fetches the chart
 * libraries only if they go somewhere that draws a chart.
 */
const AnalysisView = lazy(() =>
  import("@/components/AnalysisView").then((m) => ({ default: m.AnalysisView })),
);
const AutoResearchView = lazy(() =>
  import("@/components/AutoResearchView").then((m) => ({ default: m.AutoResearchView })),
);
const BreadthView = lazy(() =>
  import("@/components/BreadthView").then((m) => ({ default: m.BreadthView })),
);
const ConstraintsView = lazy(() =>
  import("@/components/ConstraintsView").then((m) => ({ default: m.ConstraintsView })),
);
const Dashboard = lazy(() =>
  import("@/components/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const DecideView = lazy(() =>
  import("@/components/DecideView").then((m) => ({ default: m.DecideView })),
);
const DocsView = lazy(() =>
  import("@/components/DocsView").then((m) => ({ default: m.DocsView })),
);
const OptimizeView = lazy(() =>
  import("@/components/OptimizeView").then((m) => ({ default: m.OptimizeView })),
);
const PortfolioView = lazy(() => import("@/components/PortfolioView"));
const ResearchReport = lazy(() =>
  import("@/components/ResearchReport").then((m) => ({ default: m.ResearchReport })),
);
const ScreenersView = lazy(() =>
  import("@/components/ScreenersView").then((m) => ({ default: m.ScreenersView })),
);
const SetupView = lazy(() =>
  import("@/components/SetupView").then((m) => ({ default: m.SetupView })),
);
const ValueRiskView = lazy(() =>
  import("@/components/ValueRiskView").then((m) => ({ default: m.ValueRiskView })),
);
const YourLensView = lazy(() =>
  import("@/components/YourLensView").then((m) => ({ default: m.YourLensView })),
);

/**
 * The same wording and micro-label treatment BackendGate uses for its own
 * wait, so a chunk arriving and a health check replying do not look like two
 * different kinds of pause. It is spelled in the named tokens — `text-label`
 * and `tracking-marker` — rather than BackendGate's inline `text-[12px]` and
 * `tracking-[0.2em]`, which are two stragglers from the cleanup that collapsed
 * four near-identical tracks into `marker`. The 0.02em is invisible at 12px,
 * which is why that cleanup happened.
 *
 * The ground is a parameter because the two places this appears sit on
 * different ones, and DESIGN.md is explicit that text is always a shade of its
 * own ground. `/docs` is a reading surface and paints `bg-canvas`, the fixed
 * linen; the gated screens paint `bg-ink`, which follows the theme. One
 * hardcoded ground would therefore show the wrong one on half the routes —
 * and at night the gap is the whole way across, enamel black against linen.
 * A chunk that arrives in a colour the page is not is the flash lazy loading
 * is meant to be worth avoiding, not a new one to introduce.
 */
function ScreenLoading({ ground = "ink" }: { ground?: "ink" | "canvas" }) {
  const onCanvas = ground === "canvas";
  return (
    <div
      className={clsx(
        "flex min-h-screen items-center justify-center",
        onCanvas ? "on-canvas bg-canvas" : "bg-ink",
      )}
    >
      <p
        className={clsx(
          "font-display text-label uppercase tracking-marker",
          onCanvas ? "text-on-canvas-faint" : "text-on-ink-faint",
        )}
      >
        Loading…
      </p>
    </div>
  );
}

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
        <Route
          path="/docs"
          element={
            <Suspense fallback={<ScreenLoading ground="canvas" />}>
              <DocsView />
            </Suspense>
          }
        />
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
                <Suspense fallback={<ScreenLoading />}>
                  <AppRoutes />
                </Suspense>
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
