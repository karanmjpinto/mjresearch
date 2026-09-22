import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  type CharacteristicExposure,
  type FactorProfile,
  type FactorThemesResponse,
  type ThemeExposure,
} from "@/lib/api";
import {
  cumulative,
  fixed,
  LEG_WORD,
  legOf,
  monthLabel,
  replication,
  signedPct,
  yearsBefore,
} from "@/lib/factors";
import { CumulativeChart, ReplicationChart, Sparkline, TiltBar } from "./FactorCharts";
import { InfoTip } from "./InfoTip";

/**
 * Analysis → Factors. Where this company sits on the thirteen JKP themes, and
 * what each theme has paid.
 *
 * Two different kinds of number share this screen, and it says which is which:
 *
 *   - The theme returns are Jensen, Kelly and Pedersen's published long-short
 *     portfolios (jkpfactors.com). A century of US data, dated, and unchanged
 *     by anything this app does.
 *   - The company's tilt is ours: a percentile rank against the cached screen
 *     universes on the JKP characteristics the fetched fundamentals can
 *     measure. Fewer characteristics than JKP use, against fewer peers.
 *
 * Nothing here is a model output. It is the one tab in Analysis that is
 * measured rather than judged, and it sits here rather than under Data because
 * its use is interpretive: it says what *kind* of company the investors on the
 * next tab are arguing about, in the vocabulary the factor literature uses.
 *
 * The replication chart is the part most worth reading. JKP's paper asks
 * whether published anomalies survive outside the sample that found them; the
 * detail view asks it of every factor in the selected theme.
 */

type Window = "all" | "1972" | "2000" | "10y";

const WINDOWS: { id: Window; label: string }[] = [
  { id: "all", label: "Since 1926" },
  { id: "1972", label: "Since 1972" },
  { id: "2000", label: "Since 2000" },
  { id: "10y", label: "Last 10 years" },
];

const WEIGHTING_WORD: Record<string, string> = {
  vw_cap: "capped value-weighted",
  vw: "value-weighted",
  ew: "equal-weighted",
};

export function FactorsPanel({ ticker }: { ticker: string }) {
  const themesQ = useQuery({
    queryKey: ["factor-themes"],
    queryFn: api.getFactorThemes,
    staleTime: Infinity,
    retry: false,
  });
  const profileQ = useQuery({
    queryKey: ["factor-profile", ticker],
    queryFn: () => api.getFactorProfile(ticker),
    staleTime: 10 * 60_000,
    retry: false,
  });

  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? defaultTheme(profileQ.data) ?? "value";

  if (themesQ.isError) {
    return (
      <Notice>
        The JKP factor file is not on this server, so there is nothing to draw.
        Rebuild it with{" "}
        <code className="font-display text-label text-bone">
          uv run python scripts/refresh_jkp.py
        </code>
        .
      </Notice>
    );
  }
  if (!themesQ.data) {
    return <Notice>Loading a century of factor returns…</Notice>;
  }

  const data = themesQ.data;

  return (
    <div className="flex flex-col gap-lg">
      <SourceLine data={data} />

      <ThemeMap
        data={data}
        ticker={ticker}
        profile={profileQ.data}
        profileLoading={profileQ.isPending}
        profileError={profileQ.isError}
        selected={selected}
        onSelect={setPicked}
      />

      <ThemeDetail
        data={data}
        themeId={selected}
        ticker={ticker}
        profile={profileQ.data}
      />

      <ProfileMethod profile={profileQ.data} />
    </div>
  );
}

/**
 * Open on the theme where the company leans hardest, since that is the one a
 * reader is most likely to ask about. Value when nothing was measured.
 */
function defaultTheme(p: FactorProfile | undefined): string | null {
  if (!p) return null;
  let best: ThemeExposure | null = null;
  for (const t of p.themes) {
    if (t.score == null) continue;
    if (!best || Math.abs(t.score - 50) > Math.abs(best.score! - 50)) best = t;
  }
  return best?.id ?? null;
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-xl border border-ink-line bg-ink-raised p-md text-body-sm text-on-ink-soft">
      {children}
    </p>
  );
}

function SourceLine({ data }: { data: FactorThemesResponse }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-sm">
      <p className="max-w-measure text-body-xs text-on-ink-soft">
        Returns from{" "}
        <a
          href={data.source.url}
          target="_blank"
          rel="noreferrer"
          className="text-cobalt underline decoration-cobalt/40 underline-offset-2 hover:decoration-cobalt"
        >
          JKP Global Factor Data
        </a>{" "}
        — {data.region.toUpperCase()}, {data.frequency},{" "}
        {WEIGHTING_WORD[data.weighting] ?? data.weighting} long-short portfolios,{" "}
        {monthLabel(data.first_month)} to {monthLabel(data.last_month)}. Each
        theme is the average of its factors. {data.source.paper}.
      </p>
      <span className="shrink-0 rounded-full border border-verdigris/50 px-sm py-2xs font-display text-label uppercase tracking-label text-verdigris">
        Computed · no model
      </span>
    </div>
  );
}

// ── The map: every theme, the company's tilt, and what the theme has paid ──

function ThemeMap({
  data,
  ticker,
  profile,
  profileLoading,
  profileError,
  selected,
  onSelect,
}: {
  data: FactorThemesResponse;
  ticker: string;
  profile: FactorProfile | undefined;
  profileLoading: boolean;
  profileError: boolean;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const sparks = useMemo(
    () =>
      Object.fromEntries(data.themes.map((t) => [t.id, cumulative(t, data.months)])),
    [data],
  );
  const tilt = new Map(profile?.themes.map((t) => [t.id, t]));
  const lastYear = data.last_month.slice(0, 4);

  return (
    <section aria-labelledby="factor-map-h" className="flex flex-col gap-sm">
      <div>
        <h2
          id="factor-map-h"
          className="flex items-center gap-xs font-display text-label uppercase tracking-label text-on-ink-faint"
        >
          Factor map
          <InfoTip term="factor-tilt" />
        </h2>
        <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
          Right of centre, {ticker} is on the side of the theme JKP buy; left,
          the side they sell. The numbers are what the theme itself has paid —
          not {ticker}. Pick a row for its history and its factors.
        </p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-ink-line">
        <table className="w-full min-w-[760px] border-collapse text-left">
          <thead>
            <tr className="border-b border-ink-line font-display text-label uppercase tracking-label text-on-ink-faint">
              <th scope="col" className="px-sm py-xs font-normal">Theme</th>
              <th scope="col" className="px-sm py-xs font-normal">
                {ticker} tilt
              </th>
              <th scope="col" className="px-sm py-xs font-normal">
                $1 since {data.first_month.slice(0, 4)}, log
              </th>
              <th scope="col" className="px-sm py-xs text-right font-normal">
                A year
              </th>
              <th scope="col" className="px-sm py-xs text-right font-normal">
                Sharpe
              </th>
              <th scope="col" className="px-sm py-xs text-right font-normal">
                Last 10y
              </th>
              <th scope="col" className="px-sm py-xs text-right font-normal">
                {lastYear}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.themes.map((t) => {
              const on = t.id === selected;
              const tl = tilt.get(t.id);
              return (
                <tr
                  key={t.id}
                  className={`border-b border-ink-line/60 last:border-0 transition-colors ${
                    on ? "bg-ink-raised" : "hover:bg-ink-raised/60"
                  }`}
                >
                  <th scope="row" className="px-sm py-xs font-normal">
                    {/* The row's control. A button inside the header cell,
                        not a clickable <tr>, so it is reachable by keyboard
                        and announced as what it does. */}
                    <button
                      type="button"
                      onClick={() => onSelect(t.id)}
                      aria-pressed={on}
                      className={`text-left text-body-sm transition-colors focus-visible:outline-none focus-visible:underline ${
                        on ? "text-cadmium" : "text-bone hover:text-cadmium"
                      }`}
                    >
                      {t.name}
                    </button>
                    <span className="block text-body-xs text-on-ink-faint">
                      {t.n_factors} factors
                    </span>
                  </th>
                  <td className="px-sm py-xs">
                    <TiltCell
                      tilt={tl}
                      loading={profileLoading}
                      error={profileError}
                    />
                  </td>
                  <td className="px-sm py-xs">
                    <Sparkline points={sparks[t.id] ?? []} />
                  </td>
                  <Num>{signedPct(t.stats.full?.ann_return)}</Num>
                  <Num>{fixed(t.stats.full?.sharpe)}</Num>
                  <Num>{signedPct(t.stats.last_10y?.ann_return)}</Num>
                  <Num>{signedPct(t.stats.last_12m_return)}</Num>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-body-xs text-on-ink-faint">
        “A year” and Sharpe cover the whole history; “Last 10y” is annualised;{" "}
        {lastYear} is the compounded return of the last twelve months in the
        data.
      </p>
    </section>
  );
}

function Num({ children }: { children: React.ReactNode }) {
  return (
    <td className="tabular px-sm py-xs text-right text-body-sm text-on-ink">
      {children}
    </td>
  );
}

function TiltCell({
  tilt,
  loading,
  error,
}: {
  tilt: ThemeExposure | undefined;
  loading: boolean;
  error: boolean;
}) {
  if (loading) {
    return <span className="text-body-xs text-on-ink-faint">measuring…</span>;
  }
  if (error || !tilt) {
    return <span className="text-body-xs text-on-ink-faint">unavailable</span>;
  }
  if (tilt.score == null) {
    return (
      <span className="text-body-xs text-on-ink-faint">
        {tilt.measurable === 0 ? "not measurable here" : "no data for this name"}
      </span>
    );
  }
  const leg = legOf(tilt.score);
  return (
    <div className="flex items-center gap-xs">
      <TiltBar score={tilt.score} />
      <span className="tabular whitespace-nowrap text-body-xs text-on-ink">
        {Math.round(tilt.score)}{" "}
        <span className="text-on-ink-soft">{LEG_WORD[leg]}</span>
      </span>
      <span
        className="tabular whitespace-nowrap text-body-xs text-on-ink-faint"
        title={`${tilt.measured} of the ${tilt.jkp_factors ?? "?"} characteristics JKP use for this theme were measured`}
      >
        {tilt.measured}/{tilt.jkp_factors ?? "?"}
      </span>
    </div>
  );
}

// ── The detail: one theme's history, the company's characteristics, and ──
// ── whether each factor survived its own publication                     ──

function ThemeDetail({
  data,
  themeId,
  ticker,
  profile,
}: {
  data: FactorThemesResponse;
  themeId: string;
  ticker: string;
  profile: FactorProfile | undefined;
}) {
  const [win, setWin] = useState<Window>("all");
  const theme = data.themes.find((t) => t.id === themeId);

  const factorsQ = useQuery({
    queryKey: ["theme-factors", themeId],
    queryFn: () => api.getThemeFactors(themeId),
    staleTime: Infinity,
    retry: false,
  });

  const from =
    win === "all"
      ? undefined
      : win === "10y"
        ? yearsBefore(data.last_month, 10)
        : `${win}-01`;
  const points = useMemo(
    () => (theme ? cumulative(theme, data.months, from) : []),
    [theme, data.months, from],
  );

  if (!theme) return null;

  const tilt = profile?.themes.find((t) => t.id === themeId);
  const chars = profile?.characteristics.filter((c) => c.theme === themeId) ?? [];
  const rep = factorsQ.data ? replication(factorsQ.data.factors) : null;
  const end = points.at(-1);

  return (
    <section
      aria-labelledby="factor-detail-h"
      className="flex flex-col gap-md rounded-xl border border-ink-line bg-ink-raised p-md"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-sm">
        <div>
          <h2
            id="factor-detail-h"
            className="font-display text-display-sm tracking-tight text-bone"
          >
            {theme.name}
          </h2>
          <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
            {tiltSentence(ticker, theme.name, tilt)}
          </p>
        </div>
        <div role="group" aria-label="Window" className="flex flex-wrap gap-2xs">
          {WINDOWS.map((w) => (
            <button
              key={w.id}
              type="button"
              aria-pressed={w.id === win}
              onClick={() => setWin(w.id)}
              className={`rounded border px-sm py-2xs font-display text-label uppercase tracking-label transition-colors ${
                w.id === win
                  ? "border-cadmium text-cadmium"
                  : "border-ink-line text-on-ink-soft hover:border-cobalt hover:text-bone"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </header>

      <figure className="m-0 flex flex-col gap-xs">
        <figcaption className="text-body-xs text-on-ink-soft">
          Growth of $1 in the {theme.name.toLowerCase()} long-short portfolio,
          log scale
          {end && (
            <>
              {" "}— ${end.value >= 10 ? end.value.toFixed(0) : end.value.toFixed(2)} by{" "}
              {monthLabel(end.month)}
            </>
          )}
          .
        </figcaption>
        <CumulativeChart points={points} title={`${theme.name} long-short`} />
      </figure>

      {chars.length > 0 && (
        <CompanyCharacteristics ticker={ticker} chars={chars} />
      )}

      <div className="flex flex-col gap-xs">
        <h3 className="flex items-center gap-xs font-display text-label uppercase tracking-label text-on-ink-faint">
          Did each factor survive its own paper?
          <InfoTip term="factor-replication" />
        </h3>
        {factorsQ.isPending && (
          <p className="text-body-xs text-on-ink-faint">Loading factors…</p>
        )}
        {factorsQ.isError && (
          <p className="text-body-xs text-on-ink-faint">
            The factor list for this theme did not load.
          </p>
        )}
        {rep && rep.tested > 0 && (
          <p className="max-w-measure text-body-sm text-on-ink-soft">
            {rep.held} of {rep.tested} {theme.name.toLowerCase()} factors still
            earned a positive return after the years their original paper
            studied. The median Sharpe went from {fixed(rep.medianIn)} inside
            that sample to {fixed(rep.medianPost)} after it. Hollow is inside
            the sample, solid is after.
          </p>
        )}
        {factorsQ.data && <ReplicationChart rows={factorsQ.data.factors} />}
        {factorsQ.data && (
          <details className="text-body-xs text-on-ink-soft">
            <summary className="cursor-pointer font-display text-label uppercase tracking-label text-on-ink-faint hover:text-bone">
              As a table
            </summary>
            <div className="mt-xs overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-ink-line font-display text-label uppercase tracking-label text-on-ink-faint">
                    <th scope="col" className="py-2xs pr-sm font-normal">Factor</th>
                    <th scope="col" className="py-2xs pr-sm font-normal">Paper</th>
                    <th scope="col" className="py-2xs pr-sm font-normal">Sample</th>
                    <th scope="col" className="py-2xs pr-sm text-right font-normal">Sharpe in</th>
                    <th scope="col" className="py-2xs pr-sm text-right font-normal">Sharpe after</th>
                    <th scope="col" className="py-2xs text-right font-normal">A year after</th>
                  </tr>
                </thead>
                <tbody>
                  {factorsQ.data.factors.map((f) => (
                    <tr key={f.id} className="border-b border-ink-line/60">
                      <th scope="row" className="py-2xs pr-sm font-normal text-on-ink">
                        {f.name}{" "}
                        <span className="font-display text-label text-on-ink-faint">{f.id}</span>
                      </th>
                      <td className="py-2xs pr-sm">{f.cite ?? "—"}</td>
                      <td className="tabular py-2xs pr-sm">
                        {f.in_sample_years ? `${f.in_sample_years[0]}–${f.in_sample_years[1]}` : "—"}
                      </td>
                      <td className="tabular py-2xs pr-sm text-right">{fixed(f.in_sample?.sharpe)}</td>
                      <td className="tabular py-2xs pr-sm text-right">{fixed(f.post_sample?.sharpe)}</td>
                      <td className="tabular py-2xs text-right">{signedPct(f.post_sample?.ann_return)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </div>
    </section>
  );
}

function tiltSentence(
  ticker: string,
  name: string,
  tilt: ThemeExposure | undefined,
): string {
  if (!tilt) return `${ticker}'s position on ${name.toLowerCase()} is still being measured.`;
  if (tilt.score == null) {
    return tilt.measurable === 0
      ? `None of the characteristics behind ${name.toLowerCase()} can be measured from the data this app fetches, so ${ticker} has no reading here — which is not the same as a neutral one.`
      : `The characteristics behind ${name.toLowerCase()} that this app can measure were not available for ${ticker}.`;
  }
  const leg = legOf(tilt.score);
  const where =
    leg === "middle"
      ? "near the middle"
      : `on the ${leg} side`;
  return `${ticker} scores ${Math.round(tilt.score)} of 100 — ${where} — on ${tilt.measured} of the ${tilt.jkp_factors ?? "?"} characteristics JKP use for this theme.`;
}

function formatValue(c: CharacteristicExposure): string {
  if (c.value == null) return "—";
  if (c.id === "market_equity") {
    const v = c.value;
    return v >= 1e12
      ? `$${(v / 1e12).toFixed(2)}tn`
      : v >= 1e9
        ? `$${(v / 1e9).toFixed(1)}bn`
        : `$${(v / 1e6).toFixed(0)}m`;
  }
  if (c.id === "at_be") return `${fixed(c.value, 2)}×`;
  return signedPct(c.value, 1).replace("+", "");
}

function CompanyCharacteristics({
  ticker,
  chars,
}: {
  ticker: string;
  chars: CharacteristicExposure[];
}) {
  return (
    <div className="flex flex-col gap-xs">
      <h3 className="font-display text-label uppercase tracking-label text-on-ink-faint">
        What put {ticker} there
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-body-xs">
          <thead>
            <tr className="border-b border-ink-line font-display text-label uppercase tracking-label text-on-ink-faint">
              <th scope="col" className="py-2xs pr-sm font-normal">Characteristic</th>
              <th scope="col" className="py-2xs pr-sm text-right font-normal">{ticker}</th>
              <th scope="col" className="py-2xs pr-sm text-right font-normal">Percentile</th>
              <th scope="col" className="py-2xs pr-sm font-normal">JKP buy</th>
              <th scope="col" className="py-2xs text-right font-normal">Peers</th>
            </tr>
          </thead>
          <tbody>
            {chars.map((c) => (
              <tr key={c.id} className="border-b border-ink-line/60 align-top">
                <th scope="row" className="py-2xs pr-sm font-normal text-on-ink">
                  {c.label}{" "}
                  <span className="font-display text-label text-on-ink-faint">{c.id}</span>
                  <span className="block text-on-ink-faint">{c.formula}</span>
                  {c.approximation && (
                    <span className="block text-on-ink-soft">≈ {c.approximation}</span>
                  )}
                </th>
                <td className="tabular py-2xs pr-sm text-right text-on-ink">
                  {formatValue(c)}
                </td>
                <td className="tabular py-2xs pr-sm text-right text-on-ink">
                  {c.percentile == null ? "—" : Math.round(c.percentile)}
                </td>
                <td className="py-2xs pr-sm text-on-ink-soft">
                  {c.direction > 0 ? "the high end" : "the low end"}
                </td>
                <td className="tabular py-2xs text-right text-on-ink-soft">{c.peers}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProfileMethod({ profile }: { profile: FactorProfile | undefined }) {
  if (!profile) return null;
  const caches = profile.reference.caches;
  return (
    <section className="max-w-measure text-body-xs text-on-ink-faint">
      <h2 className="font-display text-label uppercase tracking-label text-on-ink-faint">
        How the tilt is measured
      </h2>
      <p className="mt-2xs">
        Each characteristic is ranked against the {profile.reference.names}{" "}
        names in the cached screens
        {caches.length > 0 &&
          ` (${caches
            .map((c) => `${c.universe.toUpperCase()}, built ${c.built_at.slice(0, 10)}`)
            .filter((v, i, a) => a.indexOf(v) === i)
            .join("; ")})`}
        , then flipped where JKP buy the low end, so above 50 always means the
        side the factor buys. A theme is the average of what could be measured;
        a theme with nothing measurable is left blank rather than set to 50.
        {profile.source === "live" &&
          ` ${profile.ticker} is in none of those caches, so its fields were fetched just now — a few weeks newer than its peers'.`}
        {profile.reference.names === 0 &&
          " There are no cached screens on this server, so there is nothing to rank against. Run scripts/refresh_screens.py locally."}{" "}
        A tilt describes the company; it is not a forecast that the premium
        arrives for it.
      </p>
    </section>
  );
}
