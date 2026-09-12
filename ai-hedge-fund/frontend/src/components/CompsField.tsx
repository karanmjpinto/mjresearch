import { useQuery } from "@tanstack/react-query";
import { api, type CompsBand } from "@/lib/api";
import { compsExtent, compsPct, type Extent } from "@/lib/comps-scale";

/**
 * The football field: what each peer multiple says a share is worth, drawn
 * against today's price.
 *
 * Every bar sits on one shared scale, so the comparison between methods is the
 * point rather than an accident of per-row autoscaling. A method the backend
 * judged inapplicable is still drawn — hiding a row would be its own kind of
 * lie — but dashed, labelled "excluded", and left out of the summary range.
 *
 * Numbers appear as text on every row as well as in the bars, so the chart is
 * readable without seeing the geometry or the colour.
 */

const TRACK = "relative h-6 rounded bg-ink";

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2xs">
      <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
        {label}
      </span>
      {children}
    </div>
  );
}

function Row({ band, extent }: { band: CompsBand; extent: Extent }) {
  const left = compsPct(band.low, extent);
  const width = Math.max(compsPct(band.high, extent) - left, 0.6);
  const mid = compsPct(band.mid, extent);
  const off = !band.applicable;

  return (
    <div className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-sm">
      <div className="flex flex-col">
        <span className="font-display text-label uppercase tracking-label text-on-ink">
          {band.label}
        </span>
        <span className="font-display text-label text-on-ink-soft tabular">
          {band.peer_count} peers · {band.peer_multiple.low}–{band.peer_multiple.high}×
        </span>
      </div>

      <div>
        <div className={TRACK}>
          <div
            className={`absolute inset-y-0 rounded border ${
              off ? "border-dashed border-oxide bg-oxide/10" : "border-cobalt bg-cobalt/25"
            }`}
            style={{ left: `${left}%`, width: `${width}%` }}
          />
          <div
            aria-hidden
            className={`absolute inset-y-1 w-px ${off ? "bg-oxide" : "bg-bone"}`}
            style={{ left: `${mid}%` }}
          />
        </div>
        <p className="mt-2xs font-display text-label text-on-ink-soft tabular">
          {band.low.toFixed(2)} – {band.high.toFixed(2)}
          <span className="text-on-ink-faint"> · mid {band.mid.toFixed(2)}</span>
          {off && <span className="ml-xs uppercase tracking-label text-oxide">excluded</span>}
        </p>
        {band.note && <p className="mt-2xs max-w-[68ch] text-body-xs text-oxide">{band.note}</p>}
      </div>
    </div>
  );
}

export function CompsField({ ticker }: { ticker: string }) {
  const q = useQuery({
    queryKey: ["comps-range", ticker],
    queryFn: () => api.getCompsRange(ticker),
    enabled: Boolean(ticker),
  });

  if (q.isLoading) {
    return (
      <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
        Computing the comparable range…
      </p>
    );
  }
  if (q.isError || !q.data) {
    return (
      <div className="flex flex-wrap items-center gap-sm">
        <p className="text-body-sm text-oxide">
          The comparable range could not be computed — the peers or the price were unavailable.
        </p>
        <button
          type="button"
          onClick={() => q.refetch()}
          className="shrink-0 border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
        >
          Try again
        </button>
      </div>
    );
  }

  const d = q.data;
  const s = d.summary;
  const price = d.price ?? 0;

  // One scale for every mark, price included, so the bars are comparable to
  // each other and to what you would pay today.
  const extent = compsExtent([...d.bands.flatMap((b) => [b.low, b.high]), price]);
  const pricePct = compsPct(price, extent);

  return (
    <section
      className="flex flex-col gap-md"
      aria-label={`Comparable-company value range for ${d.ticker}`}
    >
      <div className="flex flex-wrap items-end justify-between gap-sm">
        <Labelled label="Value range · $ per share">
          <p className="text-body-sm text-on-ink-soft">
            {s.available ? (
              <>
                <span className="tabular text-on-ink">
                  {s.low?.toFixed(2)} – {s.high?.toFixed(2)}
                </span>{" "}
                against a price of <span className="tabular text-cadmium">{price.toFixed(2)}</span>,
                which is <span className="text-on-ink">{s.position}</span>
                {typeof s.upside_to_mid_pct === "number" && (
                  <>
                    {" "}
                    (<span className="tabular">{s.upside_to_mid_pct.toFixed(1)}%</span> to the
                    midpoint)
                  </>
                )}
              </>
            ) : (
              (s.reason ?? "No method produced a usable range.")
            )}
          </p>
        </Labelled>
        <span
          className={`shrink-0 rounded border px-xs py-2xs font-display text-label uppercase tracking-label ${
            d.vetted ? "border-verdigris text-verdigris" : "border-ink-line text-on-ink-faint"
          }`}
          title={d.vetted ? "Peers hand-picked in config/comps.json" : "Peers inherited from SIC"}
        >
          {d.vetted ? "Curated peers" : "Unvetted peers"}
        </span>
      </div>

      {d.bands.length > 0 ? (
        <div className="relative flex flex-col gap-sm">
          {d.bands.map((b) => (
            <Row key={b.metric} band={b} extent={extent} />
          ))}
          {/* Today's price, across every row, on the shared scale. */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 border-l border-dashed border-oxide"
            style={{ left: `calc(120px + ${(pricePct / 100).toFixed(4)} * (100% - 120px))` }}
          />
        </div>
      ) : (
        <p className="text-body-sm text-on-ink-soft">
          No multiple could be inverted for this name.
        </p>
      )}

      {d.dropped.length > 0 && (
        <Labelled label="Not used">
          <ul className="flex flex-col gap-2xs">
            {d.dropped.map((x) => (
              <li key={x.metric} className="text-body-xs text-on-ink-faint">
                <span className="font-display uppercase tracking-label text-on-ink-soft">
                  {x.metric}
                </span>{" "}
                — {x.reason}
              </li>
            ))}
          </ul>
        </Labelled>
      )}

      <p className="max-w-[72ch] text-body-xs text-on-ink-faint">
        Each bar is the peer quartile range applied to the per-share figure recovered from this
        company&apos;s own multiple. Peers: {d.peers.join(", ") || "none"}
        {d.as_of && <> · set {d.as_of}</>}.
      </p>
    </section>
  );
}
