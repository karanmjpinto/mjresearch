import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { RegistrationMark } from "./PixelArtifacts";

/**
 * Says "you are not a member", which is a different fact from "the backend is
 * down".
 *
 * BackendGate already explains an unreachable API. Conflating the two would be
 * the worse error of the pair: telling someone the app runs on their own
 * machine, when the truth is that it runs here and they have not been let in,
 * sends them off to clone a repository they did not need to clone. So this
 * component owns exactly one case — a live API that refuses — and leaves the
 * unreachable case where it was.
 *
 * Sits inside BackendGate for that reason: by the time this renders, health
 * has already answered, so a 401 here can only mean membership.
 *
 * Renders nothing at all when the gate is switched off, which is every local
 * checkout. The door only exists where there is something behind it.
 */
export function MemberGate({ children }: { children: React.ReactNode }) {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 60_000,
  });

  // Nothing is said while this is in flight. BackendGate has already drawn a
  // "connecting" state for the request before this one, and a second full-page
  // spinner behind the first reads as two separate waits for one page load.
  if (me.isLoading) return null;

  // The query itself failing is not a membership answer — `/api/me` is exempt
  // from the gate, so an error here is a transport problem. Let the app render
  // and let the individual panels report their own failures, which is what
  // happened before membership existed.
  if (me.isError) return <>{children}</>;

  if (!me.data?.gate_enabled || me.data.member) return <>{children}</>;

  return (
    <div className="flex min-h-dvh items-center justify-center bg-ink px-6">
      <div className="w-full max-w-xl">
        <RegistrationMark className="mb-xl text-on-ink-faint/50" />

        <span className="inline-block bg-cadmium px-sm py-2xs font-display text-label uppercase tracking-label text-on-accent">
          Invite only
        </span>

        <h1 className="mt-lg font-display text-display-sm leading-tight tracking-tight text-bone">
          You need a link from someone already inside
        </h1>

        <p className="mt-md max-w-[60ch] text-[15px] leading-relaxed text-on-ink-soft">
          There is no sign-up form, and no waitlist to join. The only way in is
          a single-use link sent to you by someone who is already a member. Each
          one opens once.
        </p>

        <p className="mt-md max-w-[60ch] text-[15px] leading-relaxed text-on-ink-soft">
          The reason is cost rather than mystique: every analysis run here calls
          a paid model on the owner&rsquo;s account, so a seat is a standing
          expense and comes with a monthly allowance attached to a name.
        </p>

        <div className="mt-2xl flex flex-wrap gap-sm font-display text-label uppercase tracking-label">
          <Link
            to="/"
            className="bg-bone px-6 py-3.5 text-on-accent transition-colors duration-300 ease-out-expo hover:bg-cadmium"
          >
            What this is
          </Link>
          <Link
            to="/docs"
            className="border border-ink-line px-6 py-3.5 text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
          >
            Read the reference
          </Link>
        </div>

        <p className="mt-xl max-w-[60ch] text-label leading-relaxed text-on-ink-faint">
          Both of those are open to everyone, and between them they describe
          what the app computes, what it merely writes, and what it cannot do.
          Nothing behind the door is hidden from the reference section.
        </p>
      </div>
    </div>
  );
}
