import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppNav } from "@/components/AppNav";
import { api, type SetupKey } from "@/lib/api";

/**
 * Setup.
 *
 * The framing matters: nothing here is required. The app runs on keyless
 * providers and a local model by default, so this screen reports what each key
 * would *add* rather than nagging about what is missing. A setup screen that
 * looks like a wall of unmet requirements makes a working install feel broken.
 *
 * Keys are write-only. The server reports whether a value exists and never
 * returns it, so nothing here can read back a secret already on disk.
 */

function StatusPip({ on, label }: { on: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-2xs">
      <span className={`h-1.5 w-1.5 rounded-full ${on ? "bg-verdigris" : "bg-on-ink-faint"}`} />
      <span className="font-display text-label uppercase tracking-[0.12em] text-on-ink-faint">
        {label}
      </span>
    </span>
  );
}

function KeyRow({
  spec,
  value,
  onChange,
}: {
  spec: SetupKey;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="border-t border-ink-line px-lg py-md first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-sm">
        <div className="flex items-baseline gap-sm">
          <span className="font-display text-[14px] text-bone">{spec.label}</span>
          <span className="font-display text-label uppercase tracking-[0.12em] text-on-ink-faint">
            {spec.env}
          </span>
          {spec.free_tier && (
            <span className="bg-verdigris/15 px-1.5 py-0.5 font-display text-label uppercase tracking-[0.1em] text-verdigris">
              free tier
            </span>
          )}
        </div>
        <StatusPip on={spec.configured} label={spec.configured ? "configured" : "not set"} />
      </div>

      <p className="mt-2xs max-w-[70ch] text-[13px] leading-relaxed text-on-ink-soft">
        {spec.unlocks}
      </p>

      <div className="mt-sm flex flex-wrap items-center gap-sm">
        <input
          type={spec.secret ? "password" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={spec.configured ? "•••••••• (set — type to replace)" : "paste value to enable"}
          autoComplete="off"
          spellCheck={false}
          className="min-w-[260px] flex-1 border border-ink-line bg-ink px-3 py-2 font-display text-[12px] text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
        />
        <a
          href={spec.signup}
          target="_blank"
          rel="noreferrer"
          className="font-display text-label uppercase tracking-[0.12em] text-cobalt transition-colors hover:text-cadmium"
        >
          Get key →
        </a>
      </div>
    </div>
  );
}

export function SetupView() {
  const qc = useQueryClient();
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api.getSetup() });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<string[] | null>(null);

  useEffect(() => {
    if (saved) {
      const t = setTimeout(() => setSaved(null), 8000);
      return () => clearTimeout(t);
    }
  }, [saved]);

  const save = useMutation({
    mutationFn: () =>
      api.saveKeys(
        Object.entries(draft)
          .filter(([, v]) => v.trim())
          .map(([env, value]) => ({ env, value: value.trim() }))
      ),
    onSuccess: (r) => {
      setSaved(r.written);
      setDraft({});
      qc.invalidateQueries({ queryKey: ["setup"] });
    },
  });

  const pending = Object.values(draft).filter((v) => v.trim()).length;
  const d = setup.data;

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="setup" />

      <main className="mx-auto max-w-4xl px-lg py-xl">
        <header className="mb-lg">
          <h1 className="font-display text-display-sm tracking-tight text-bone">Setup</h1>
          <p className="mt-sm max-w-[68ch] text-[15px] leading-relaxed text-on-ink-soft">
            Everything here is optional. The app works with no keys at all — prices,
            fundamentals, filings and the local model are already running. Each key below
            adds coverage on top of that.
          </p>
        </header>

        {setup.isLoading && <p className="text-[13px] text-on-ink-faint">Loading…</p>}
        {setup.isError && (
          <p className="text-[13px] text-oxide">Could not read setup: {(setup.error as Error).message}</p>
        )}

        {d && (
          <>
            <div className="mb-lg grid gap-px bg-ink-line sm:grid-cols-3">
              {[
                { n: `${d.summary.providers_working}/${d.summary.providers_total}`, l: "data providers live" },
                { n: `${d.summary.keys_configured}/${d.summary.keys_total}`, l: "optional keys set" },
                { n: d.llm.model, l: `model via ${d.llm.provider}` },
              ].map((s) => (
                <div key={s.l} className="bg-ink-raised px-lg py-md">
                  <div className="font-display text-[22px] tabular text-cadmium">{s.n}</div>
                  <div className="mt-2xs font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                    {s.l}
                  </div>
                </div>
              ))}
            </div>

            <section className="border border-ink-line bg-ink-raised">
              <div className="border-b border-ink-line px-lg py-sm">
                <h2 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
                  Optional keys
                </h2>
              </div>
              {d.keys.map((k) => (
                <KeyRow
                  key={k.env}
                  spec={k}
                  value={draft[k.env] ?? ""}
                  onChange={(v) => setDraft((prev) => ({ ...prev, [k.env]: v }))}
                />
              ))}

              <div className="flex flex-wrap items-center gap-md border-t border-ink-line px-lg py-md">
                <button
                  type="button"
                  onClick={() => save.mutate()}
                  disabled={!pending || save.isPending}
                  className="bg-cobalt px-5 py-2.5 font-display text-label uppercase tracking-[0.14em] text-bone transition-colors hover:bg-cadmium hover:text-ink disabled:bg-ink-line disabled:text-on-ink-faint"
                >
                  {save.isPending ? "Saving…" : `Save ${pending || ""} key${pending === 1 ? "" : "s"}`}
                </button>
                <span className="text-[12px] text-on-ink-faint">
                  Written to <span className="font-display text-on-ink-soft">{d.env_path}</span>
                </span>
              </div>
            </section>

            {saved && (
              <div className="mt-md border border-cadmium/40 bg-cadmium/10 px-lg py-md">
                <p className="font-display text-label uppercase tracking-[0.14em] text-cadmium">
                  Saved — restart required
                </p>
                <p className="mt-2xs text-[13px] leading-relaxed text-on-ink-soft">
                  {saved.join(", ")} written. Providers read keys once at start-up, so restart the
                  API (Ctrl-C then <span className="font-display">./start.sh</span>) before they
                  take effect.
                </p>
              </div>
            )}
            {save.isError && (
              <p className="mt-md text-[13px] text-oxide">{(save.error as Error).message}</p>
            )}

            <section className="mt-xl">
              <h2 className="mb-sm font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
                Providers
              </h2>
              <div className="grid gap-px bg-ink-line sm:grid-cols-2">
                {d.providers.map((p) => (
                  <div key={p.name} className="flex items-baseline justify-between bg-ink-raised px-lg py-sm">
                    <span className="font-display text-[13px] text-bone">{p.name}</span>
                    <span className="flex items-center gap-sm">
                      <span className="text-[12px] text-on-ink-faint">{p.categories.length} categories</span>
                      <StatusPip on={p.available} label={p.available ? "live" : "needs key"} />
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
