import { Component, type ReactNode } from "react";
import clsx from "clsx";

/**
 * Catches a screen that failed to arrive, and offers the one thing that fixes it.
 *
 * The screens are lazy chunks, which buys a much smaller first load and costs
 * one new failure: the chunk itself can fail to fetch. That is not a rare
 * network event — it is the ordinary consequence of a deploy. A visitor with
 * the page already open holds an `index.html` naming hashed files that the new
 * build has replaced, so the first route they navigate to 404s, and the app
 * stops at a wait that never ends.
 *
 * The root Sentry boundary does catch it, but it takes the whole shell down to
 * do so. Here the failure stays inside the route, and the button does a hard
 * reload — which re-fetches `index.html` and is the actual repair, not a
 * gesture at one.
 */

interface Props {
  children: ReactNode;
  ground?: "ink" | "canvas";
}

interface State {
  failed: boolean;
}

export class ChunkErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;

    const onCanvas = this.props.ground === "canvas";
    return (
      <div
        className={clsx(
          "flex min-h-screen flex-col items-center justify-center gap-md px-md text-center",
          onCanvas ? "on-canvas bg-canvas" : "bg-ink",
        )}
      >
        <p
          className={clsx(
            "font-display text-label uppercase tracking-marker",
            onCanvas ? "text-on-canvas-faint" : "text-on-ink-faint",
          )}
        >
          This screen did not load
        </p>
        <p
          className={clsx(
            "max-w-prose text-sm",
            onCanvas ? "text-on-canvas-soft" : "text-on-ink-soft",
          )}
        >
          Usually this means the app was updated while this page was open, and the
          version you are holding points at files that have been replaced.
          Reloading fetches the current one.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className={clsx(
            "font-display text-label uppercase tracking-marker underline underline-offset-4",
            onCanvas
              ? "on-canvas text-on-canvas hover:text-on-canvas-soft"
              : "text-on-ink hover:text-on-ink-soft",
          )}
        >
          Reload
        </button>
      </div>
    );
  }
}
