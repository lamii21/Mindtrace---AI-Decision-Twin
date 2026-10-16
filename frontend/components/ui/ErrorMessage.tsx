import { ApiError } from "@/lib/api/client";

/** Renders the backend's real `problem+json` detail - never a fabricated message. */
export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const detail =
    error instanceof ApiError
      ? error.problem.detail || error.problem.title
      : error instanceof Error
        ? error.message
        : "Something went wrong.";

  return (
    <div className="rounded-xl border border-coral-500/30 bg-coral-500/10 px-4 py-3 text-sm text-coral-400">
      {detail}
    </div>
  );
}
