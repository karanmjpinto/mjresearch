import { useState } from "react";
import { InfoTip } from "./InfoTip";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type OnePager } from "@/lib/api";

/**
 * A page for this company, written back into the vault.
 *
 * Every other panel in this app reads. This one writes a file into somebody's
 * real Obsidian folder, and the interface is shaped around that being
 * different in kind:
 *
 *   - the note is shown in full before anything is written, so nothing is
 *     created that the reader has not already read
 *   - the write is one explicit press, never a side effect of arriving here
 *   - an existing page is reported as existing, and the control disables
 *     rather than offering to replace it
 *
 * The server enforces all three independently — a disabled button is a
 * courtesy, not a guarantee, and the endpoint refuses to overwrite regardless
 * of what the client believes.
 *
 * It uses the reader's own template when the vault has one, and says which.
 * A note in this codebase's shape would be a foreign object in a vault with
 * its own conventions, and the point of writing into a vault rather than
 * exporting a file is that the result belongs there.
 */

export function OnePagerPanel({ ticker }: { ticker: string }) {
  const [showMarkdown, setShowMarkdown] = useState(false);
  const qc = useQueryClient();

  const preview = useQuery({
    queryKey: ["one-pager", ticker],
    queryFn: () => api.getOnePager(ticker),
    enabled: Boolean(ticker),
    retry: false,
  });

  const save = useMutation({
    mutationFn: () => api.writeOnePager(ticker),
    onSuccess: () => {
      // Re-read the preview so `exists` flips and the control locks. Without
      // this the button stays live and the next press hits a 409.
      void qc.invalidateQueries({ queryKey: ["one-pager", ticker] });
    },
  });

  const d: OnePager | undefined = preview.data;
  const ready = d?.available === true;

  return (
    <section className="flex flex-col gap-sm" aria-label="One pager">
      <div>
        <h2 className="flex items-center gap-xs font-display text-label uppercase tracking-label text-on-ink-faint">
          A page for this name
          <InfoTip term="one-pager" />
        </h2>
        <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
          Nothing written about {ticker} yet? This drafts one in your own
          template, pre-linked to the notes that matched, and puts it in the
          vault where you will find it again.
        </p>
      </div>

      {preview.isLoading && (
        <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Drafting…
        </p>
      )}

      {d?.available === false && (
        <div className="border border-dashed border-ink-line bg-ink-raised p-md">
          <p className="font-display text-label uppercase tracking-label text-cadmium">
            Nothing to write to
          </p>
          <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
            {d.reason}
          </p>
        </div>
      )}

      {ready && (
        <div className="border border-ink-line bg-ink-raised p-md shadow-elev-1">
          <div className="flex flex-wrap items-baseline justify-between gap-md">
            <div className="min-w-0">
              <p className="font-display text-mark text-bone">{d.title}</p>
              <p className="mt-2xs font-display text-label text-on-ink-faint">
                {d.relative_path}
              </p>
              <p className="mt-2xs max-w-[60ch] text-body-xs text-on-ink-faint">
                {d.template
                  ? `Using your own “${d.template}” template — its headings and frontmatter are kept as they are.`
                  : "No one-pager template found in the vault, so this uses a plain shape. Add a note called “Value One Pager” and it will be used instead."}
              </p>
            </div>

            <div className="flex shrink-0 flex-col items-end gap-2xs">
              <button
                type="button"
                onClick={() => save.mutate()}
                disabled={d.exists || save.isPending || save.isSuccess}
                className="border border-ink-line px-md py-2 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-verdigris hover:text-verdigris focus-visible:border-verdigris focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                {save.isSuccess
                  ? "Written"
                  : save.isPending
                    ? "Writing…"
                    : d.exists
                      ? "Already there"
                      : "Write to vault"}
              </button>
              <button
                type="button"
                onClick={() => setShowMarkdown((v) => !v)}
                aria-expanded={showMarkdown}
                className="font-display text-label uppercase tracking-label text-on-ink-faint underline decoration-dotted transition-colors hover:text-cadmium"
              >
                {showMarkdown ? "Hide the note" : "Read it first"}
              </button>
            </div>
          </div>

          {d.exists && !save.isSuccess && (
            <p className="mt-sm border-t border-ink-line pt-sm max-w-measure text-body-xs text-cadmium">
              A page already exists at that path. It will not be replaced —
              rename or move it if you want a fresh one, since anything you
              added by hand only exists there.
            </p>
          )}

          {save.error && (
            <p className="mt-sm border-t border-ink-line pt-sm max-w-measure text-body-xs text-oxide">
              {save.error instanceof Error
                ? save.error.message
                : "Could not write the note."}
            </p>
          )}

          {save.isSuccess && (
            <p className="mt-sm border-t border-ink-line pt-sm max-w-measure text-body-xs text-verdigris">
              Written to {d.relative_path}. Open your vault and it will be
              there, linked to the notes that matched.
            </p>
          )}

          {showMarkdown && (
            <pre className="mt-sm max-h-[420px] overflow-auto border-t border-ink-line pt-sm text-body-xs leading-relaxed text-on-ink-soft">
              {d.markdown}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}
