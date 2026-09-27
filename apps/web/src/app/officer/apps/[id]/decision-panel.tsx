// Decision panel (J3): plain form -> postDecisionAction (works without JS).
// Human-in-the-loop: the agent only recommended; this is the decision record.

import { postDecisionAction } from "../../actions";

const BUTTONS = [
  { value: "approve", label: "Approve", className: "bg-emerald-600 hover:bg-emerald-500" },
  { value: "request_info", label: "Request info", className: "bg-amber-500 hover:bg-amber-400" },
  { value: "reject", label: "Reject", className: "bg-red-600 hover:bg-red-500" },
];

export function DecisionPanel({
  applicationId,
  disabled,
}: {
  applicationId: string;
  disabled: boolean;
}) {
  return (
    <form
      action={postDecisionAction}
      className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4"
    >
      <h2 className="text-sm font-semibold">Officer decision</h2>
      <input type="hidden" name="applicationId" value={applicationId} />
      <label htmlFor="officerNotes" className="block text-xs text-zinc-500">
        Notes (required for reject, shown to the citizen)
      </label>
      <textarea
        id="officerNotes"
        name="officerNotes"
        rows={3}
        defaultValue=""
        disabled={disabled}
        className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none focus:ring-1 focus:ring-zinc-900 disabled:bg-zinc-50"
      />
      <div className="grid grid-cols-1 gap-2">
        {BUTTONS.map((b) => (
          <button
            key={b.value}
            type="submit"
            name="decision"
            value={b.value}
            disabled={disabled}
            className={`min-h-12 rounded-md px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40 ${b.className}`}
          >
            {b.label}
          </button>
        ))}
      </div>
      {disabled && (
        <p className="text-xs text-zinc-500">
          This application already has a decision or an info request on record.
        </p>
      )}
    </form>
  );
}
