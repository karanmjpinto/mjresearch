import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/**
 * Who you are signed in as, and how much of this month you have spent.
 *
 * The spend half is the point. A cap the member cannot see is a trap whose
 * first symptom is a refusal in the middle of an analysis — the work appears
 * to fail for no reason, and the real reason happened silently over the
 * preceding fortnight. Showing the number costs one line of chrome and turns
 * that cliff into a slope.
 *
 * Renders nothing when the gate is off, which is every local checkout: there
 * is no member, no budget and nothing to report, and a badge saying "unlimited"
 * would just be noise in the chrome of a tool running on your own GPU.
 */
export function MemberBadge() {
  const queryClient = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.me(),
    retry: false,
    // Short enough that spend moves while you watch it, long enough that it is
    // not a request per render. A committee run takes longer than this.
    staleTime: 30_000,
  });

  if (!me.data?.gate_enabled || !me.data.member) return null;

  const { label, tokens_this_month: used, monthly_token_cap: cap } = me.data;
  const pct = cap > 0 ? Math.min(Math.round((used / cap) * 100), 100) : 100;

  // Three states rather than a gradient, because the only decisions a member
  // makes here are "carry on", "spend it carefully" and "it is gone", and a
  // continuously-varying colour does not tell them which one they are in.
  const tone =
    pct >= 100
      ? { bar: "bg-oxide", text: "text-oxide" }
      : pct >= 80
        ? { bar: "bg-cadmium", text: "text-cadmium" }
        : { bar: "bg-verdigris", text: "text-on-ink-soft" };

  async function signOut() {
    await api.logout();
    await queryClient.invalidateQueries({ queryKey: ["me"] });
    // A full load rather than a client-side navigation: every cached query in
    // the app was fetched as a member and is now unreadable, and clearing them
    // one by one is a list that would go stale.
    window.location.assign("/");
  }

  return (
    <div className="flex shrink-0 items-center gap-sm">
      {/* The visual row is hidden from assistive tech in favour of one
       * sentence below it. Three fragments read in sequence — "Jude", "/",
       * "41%" — carry no relationship to each other, and `title` on a
       * non-interactive element is not reliably announced at all, so it is a
       * hover affordance for mouse users and nothing more. The sr-only line is
       * the real accessible name. */}
      <div
        aria-hidden="true"
        className="flex items-center gap-2xs font-display text-label uppercase tracking-label"
        title={`${used.toLocaleString()} of ${cap.toLocaleString()} tokens used this month`}
      >
        <span className="text-on-ink-faint">{label}</span>
        <span className="text-on-ink-faint/50">/</span>
        <span className={`tabular ${tone.text}`}>{pct}%</span>
      </div>
      <p className="sr-only">
        Signed in as {label}. {used.toLocaleString()} of{" "}
        {cap.toLocaleString()} tokens used this month, {pct} percent of the
        allowance.
      </p>

      {/* Decorative: the number beside it is the accessible version. */}
      <div
        aria-hidden="true"
        className="h-[3px] w-16 shrink-0 overflow-hidden bg-ink-line"
      >
        <div
          className={`h-full ${tone.bar} transition-[width] duration-300 ease-out-expo`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <button
        type="button"
        onClick={signOut}
        className="shrink-0 border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-oxide hover:text-bone focus-visible:border-oxide focus-visible:outline-none"
      >
        Sign out
      </button>
    </div>
  );
}
