import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { ScreenResults } from "./ScreenResults";

/**
 * This week's curated buy-side ideas, then our own screen over them.
 *
 * Two halves on purpose. The list is what other people think is interesting;
 * the table under it is what our arithmetic makes of the same names. Bolton is
 * the screen because the feed leans to special situations, and a written-up
 * catalyst on a name that also clears his cheap-unloved-solvent test is the
 * one combination neither half finds alone.
 */
export function BuySideIdeas() {
  const q = useQuery({
    queryKey: ["commentary-ideas"],
    queryFn: api.getCommentaryIdeas,
    retry: false,
    staleTime: 30 * 60_000,
  });
  const d = q.data;

  return (
    <div className="flex flex-col gap-lg">
      <section aria-labelledby="ideas-heading" className="flex flex-col gap-sm">
        <div>
          <h2
            id="ideas-heading"
            className="font-display text-label uppercase tracking-label text-on-ink-faint"
          >
            What the buy-side wrote about this week
          </h2>
          <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
            Every name in the{" "}
            <a
              href="https://bullpen.news/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-cobalt underline-offset-2 hover:text-cadmium hover:underline"
            >
              Bullpen.News
              <span className="sr-only"> (opens in a new tab)</span>
            </a>{" "}
            feed, written-up catalysts first. Names outside the S&P 1500 are
            marked new: no screen of ours has seen them.
          </p>
        </div>

        {q.isLoading && <p className="text-body-sm text-on-ink-soft">Reading the feed…</p>}
        {q.isError && (
          <p className="text-body-sm text-oxide">
            The Bullpen.News feed could not be read just now.
          </p>
        )}

        {d && (
          <div className="overflow-x-auto border border-ink-line bg-ink-raised">
            <table className="w-full min-w-[520px] border-collapse">
              <caption className="sr-only">
                {d.ideas.length} names from {d.items} items
              </caption>
              <thead>
                <tr className="border-b border-ink-line">
                  {["Ticker", "Catalyst", "Who wrote it", "Latest"].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-md py-xs text-left font-display text-label uppercase tracking-label text-on-ink-faint"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.ideas.map((idea) => {
                  const latest = idea.items[0];
                  return (
                    <tr key={idea.ticker} className="border-b border-ink-line last:border-b-0">
                      <td className="px-md py-xs align-top">
                        <Link
                          to={`/research/${encodeURIComponent(idea.ticker)}?tab=Buy-side`}
                          className="font-display text-mark text-cobalt transition-colors hover:text-cadmium"
                        >
                          {idea.ticker}
                        </Link>
                        {idea.in_universe === false && (
                          <span className="ml-xs font-display text-label uppercase tracking-label text-cadmium">
                            new
                          </span>
                        )}
                      </td>
                      <td className="px-md py-xs align-top text-body-xs text-on-ink-soft">
                        {idea.catalyst.length ? idea.catalyst.join(", ") : "—"}
                      </td>
                      <td className="px-md py-xs align-top text-body-xs text-on-ink-soft">
                        {idea.sources.join(", ")}
                      </td>
                      <td className="px-md py-xs align-top text-body-xs">
                        {latest?.url ? (
                          <a
                            href={latest.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block max-w-measure-sm text-cobalt underline-offset-2 hover:text-cadmium hover:underline"
                          >
                            {latest.title}
                            <span className="sr-only"> (opens in a new tab)</span>
                          </a>
                        ) : (
                          <span className="text-on-ink-soft">{latest?.title}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <ScreenResults
        screen="bolton-contrarian"
        universe="bullpen_week"
        title="The same names, through the Bolton screen"
        blurb="Cheap, out of favour and solvent, among this week's names. Rows that pass carry any catalyst the buy-side has written up — a lead to read, never a score."
        info="screen-bolton"
        scoreMax={100}
      />
    </div>
  );
}
