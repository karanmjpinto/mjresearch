import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import { RegistrationMark } from "./PixelArtifacts";

/**
 * Spends an invite and signs the browser in.
 *
 * The secret arrives in the URL **fragment** — `/join#<secret>` — not the
 * path. That is the whole reason this screen reads `location.hash` instead of
 * taking a route parameter. A path is sent to the server, so it would be
 * written into uvicorn's access log, Railway's, Cloudflare's, the browser's
 * own history, and any outbound `Referer`; a fragment is never transmitted at
 * all. The one place it does persist is history, which is why the hash is
 * stripped with `replaceState` the moment it has been read.
 *
 * There is no form here on purpose. The invite link *is* the login: no email,
 * no password, no address to verify. For twenty people that is both less code
 * and a better feeling than an account system — it reads as being handed a key
 * rather than filling in a form.
 */

type State =
  | { kind: "working" }
  | { kind: "done"; label: string }
  | { kind: "missing" }
  | { kind: "refused"; reason: string; message: string };

/** What the three refusals are actually called, in plain words. */
const HEADING: Record<string, string> = {
  used: "That invite has already been opened",
  expired: "That invite has expired",
  withdrawn: "That invite was withdrawn",
  unknown: "That is not an invite to this site",
  rate_limited: "Too many attempts",
};

export function JoinView() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ kind: "working" });

  // Strict mode mounts effects twice in development. An invite opens exactly
  // once, so a second POST would consume nothing and report "already used" for
  // a link that had just worked — the user would see a failure for a success.
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;

    const secret = window.location.hash.replace(/^#/, "").trim();
    if (!secret) {
      setState({ kind: "missing" });
      return;
    }

    // Out of the address bar and out of history before the network call, so a
    // closed tab or a failed request does not leave the secret sitting there.
    window.history.replaceState(null, "", "/join");

    api
      .join(secret)
      .then(async (result) => {
        setState({ kind: "done", label: result.label });
        // The gate asks `/api/me`; that answer is now stale by one membership.
        await queryClient.invalidateQueries({ queryKey: ["me"] });
        navigate("/dashboard", { replace: true });
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.reason) {
          setState({
            kind: "refused",
            reason: error.reason,
            message: error.message,
          });
          return;
        }
        setState({
          kind: "refused",
          reason: "unknown",
          message:
            error instanceof Error
              ? error.message
              : "Something went wrong opening that invite.",
        });
      });
  }, [navigate, queryClient]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-ink px-6">
      <div className="w-full max-w-xl">
        <RegistrationMark className="mb-xl text-on-ink-faint/50" />

        {state.kind === "working" && (
          <p
            /* The only thing on screen, so it is the live region. */
            aria-live="polite"
            className="font-display text-label uppercase tracking-label text-on-ink-faint"
          >
            Opening your invite…
          </p>
        )}

        {state.kind === "done" && (
          <>
            <span className="inline-block bg-verdigris px-sm py-2xs font-display text-label uppercase tracking-label text-on-accent">
              You are in
            </span>
            <h1 className="mt-lg font-display text-display-sm leading-tight tracking-tight text-bone">
              Welcome, {state.label}
            </h1>
            <p className="mt-md text-[15px] leading-relaxed text-on-ink-soft">
              Taking you to the desk.
            </p>
          </>
        )}

        {state.kind === "missing" && (
          <>
            <span className="inline-block bg-cadmium px-sm py-2xs font-display text-label uppercase tracking-label text-on-accent">
              Nothing to open
            </span>
            <h1 className="mt-lg max-w-[24ch] font-display text-display-sm leading-tight tracking-tight text-bone">
              This page needs the whole link
            </h1>
            <p className="mt-md max-w-[60ch] text-[15px] leading-relaxed text-on-ink-soft">
              An invite link carries its key after a <code>#</code>. If you
              copied the address by hand, or a messaging app trimmed it, the
              part that matters is the bit that got cut. Paste the original link
              rather than retyping it.
            </p>
          </>
        )}

        {state.kind === "refused" && (
          <>
            <span className="inline-block bg-oxide px-sm py-2xs font-display text-label uppercase tracking-label text-on-accent">
              Not opened
            </span>
            <h1 className="mt-lg max-w-[26ch] font-display text-display-sm leading-tight tracking-tight text-bone">
              {HEADING[state.reason] ?? "That invite could not be opened"}
            </h1>
            <p className="mt-md max-w-[60ch] text-[15px] leading-relaxed text-on-ink-soft">
              {state.message}
            </p>

            {/* The only recovery that actually exists. There is no "request
             * access" form to send them to on purpose — the whole model is
             * that a person vouches for a person — so the next step is naming
             * who to go back to rather than offering a button that would queue
             * a request nobody reads. Shown only for the two reasons where a
             * fresh link is the fix; an unknown token means they were never
             * the intended recipient, and telling them to ask again would be
             * sending them to someone who did not invite them. And a
             * withdrawn invite was taken back deliberately, so telling the
             * holder to ask again would send them to argue with the person who
             * just revoked it. */}
            {(state.reason === "used" || state.reason === "expired") && (
              <p className="mt-lg max-w-[60ch] border-l-2 border-cadmium pl-md text-[15px] leading-relaxed text-on-ink">
                Go back to whoever sent you this and ask them to mint a new
                one. They take a few seconds to issue, and there is no queue
                and no approval step behind it.
              </p>
            )}

            <p className="mt-xl max-w-[60ch] text-label leading-relaxed text-on-ink-faint">
              The overview and the reference section are open to everyone in the
              meantime, and between them they describe everything the app does.
            </p>
            <div className="mt-lg flex flex-wrap gap-sm font-display text-label uppercase tracking-label">
              <a
                href="/"
                className="bg-bone px-6 py-3.5 text-on-accent transition-colors duration-300 ease-out-expo hover:bg-cadmium"
              >
                What this is
              </a>
              <a
                href="/docs"
                className="border border-ink-line px-6 py-3.5 text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
              >
                Read the reference
              </a>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
