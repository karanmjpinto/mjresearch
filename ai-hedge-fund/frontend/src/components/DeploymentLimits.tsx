import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * Says what this particular deployment cannot do, and why.
 *
 * The published site is not the app. It serves the same code against a
 * different configuration: model analysis is switched off there, and the screen
 * cache is built by a local refresh so it is empty. Both are deliberate — the
 * analysis would otherwise run on a paid gateway billed to whoever deployed the
 * site — but a visitor cannot tell "deliberately unavailable" from "broken",
 * and an empty screen with no explanation reads as the latter.
 *
 * Every claim here is read from the API's own reported state rather than
 * hardcoded, for two reasons. A notice that says "screens are empty" while
 * screens are full is worse than no notice, and this file should not need
 * editing when the deployment changes. It follows that the whole thing renders
 * nothing when nothing is limited, which is the normal case locally.
 *
 * Deliberately NOT claimed: that the portfolio is empty. On the hosted site it
 * is, but a local user who has recorded no positions is also empty, and the API
 * cannot distinguish the two. Asserting it would be the kind of plausible,
 * unverifiable statement the rest of this app exists to avoid.
 */
export function DeploymentLimits() {
  const setup = useQuery({
    queryKey: ["setup"],
    queryFn: () => api.getSetup(),
    retry: false,
    staleTime: 300_000,
  });
  const screens = useQuery({
    queryKey: ["cached-screens"],
    queryFn: () => api.getCachedScreens(),
    retry: false,
    staleTime: 300_000,
  });

  // Silence while unknown. A notice that flashes on every page load, or that
  // appears because one request failed, trains people to ignore it.
  if (setup.isLoading || screens.isLoading) return null;

  const llm = setup.data?.llm;
  const modelOff = llm?.endpoints_enabled === false;
  const noScreens = (screens.data?.screens?.length ?? 0) === 0;

  if (!modelOff && !noScreens) return null;

  const missing: { what: string; detail: string }[] = [];

  if (modelOff) {
    missing.push({
      what: "Research a ticker, and the investor committee",
      detail:
        "The part that reads a company and argues about it. Needs a model running on your own machine.",
    });
    missing.push({
      what: "The plan pipeline",
      detail: "The staged version of the same thing, with a written verdict at the end.",
    });
    missing.push({
      what: "Backtest",
      detail: "Replays the committee over history, so it costs many runs rather than one.",
    });
    missing.push({
      what: "Autoresearch",
      detail: "The unattended loop. The most expensive of the four, and the least suitable to run for a stranger.",
    });
  }

  if (noScreens) {
    missing.push({
      what: "Screen results",
      detail:
        "The three screens will list no names here. They are computed by a refresh against a market data provider and cached on the machine that ran it; this deployment has no cache. The screens' rules and thresholds are still documented in full.",
    });
  }

  return (
    <section
      aria-label="What this deployment cannot do"
      className="border-b border-ink-line bg-ink-raised px-lg py-md"
    >
      <div className="mx-auto max-w-measure">
        <span className="inline-block bg-cadmium px-sm py-2xs font-display text-label uppercase tracking-label text-on-accent">
          Not everything here works
        </span>

        <p className="mt-md max-w-measure-sm text-body-sm text-on-ink-soft">
          {modelOff ? (
            <>
              This is the published site, and it deliberately does not run the model. Anything
              below is empty or unavailable by design rather than broken — and the reason is the
              one on the front page: the analysis is meant to run on your machine, against your
              own model, with nothing leaving your computer.
            </>
          ) : (
            <>
              Some of what follows has no data on this deployment. It is not broken — the missing
              pieces are computed locally and cached on the machine that computed them.
            </>
          )}
        </p>

        <dl className="mt-lg space-y-md">
          {missing.map(({ what, detail }) => (
            <div key={what}>
              <dt className="font-display text-mark text-bone">{what}</dt>
              <dd className="mt-2xs max-w-measure-sm text-body-xs text-on-ink-faint">
                {detail}
              </dd>
            </div>
          ))}
        </dl>

        <p className="mt-lg max-w-measure-sm text-body-xs text-on-ink-faint">
          Everything else on this page is real: the methodology, the scoring rules, the
          documented gaps, and any figure shown is computed the same way it would be locally.{" "}
          {/* Not an accent hue. Measured on `bg-ink-raised` in both themes, no
              theme-following accent clears 4.5:1 on both grounds: cadmium is
              4.23 in daylight, and cobalt — which Dashboard uses for a link —
              is 3.78 in the dark. `bone` is 16.72 / 14.65, and the underline is
              what marks this as a link, so the hue was not carrying the
              meaning anyway. */}
          <a
            className="text-bone underline decoration-from-font underline-offset-2"
            href="/docs"
          >
            What is computed and what is written
          </a>{" "}
          sets out which is which.
        </p>
      </div>
    </section>
  );
}
