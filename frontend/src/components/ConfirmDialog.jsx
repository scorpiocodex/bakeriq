/**
 * Generic confirmation dialog.
 *
 * Used for "are you sure you want to deactivate this customer?" today,
 * and any future destructive action: deleting a product, cancelling
 * an order, voiding a billing export.
 *
 * Why generic and not a CustomerDeactivateDialog:
 *   The same UI pattern (title, message, two buttons) appears for every
 *   destructive action. One reusable component means consistent styling
 *   everywhere AND only one place to update if the design system changes.
 *
 * Why not the browser's native confirm():
 *   Native confirm() works but doesn't match our design system. Also
 *   blocks the entire JS thread, which can hide background activity.
 */
export default function ConfirmDialog({
    open,
    title,
    message,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    destructive = false,
    onConfirm,
    onCancel,
    isProcessing = false,
}) {
    if (!open) return null;

    // The destructive flag swaps the confirm button from blue (default)
    // to red. Visual cue: this action is irreversible-ish; double-check.
    const confirmClasses = destructive
        ? 'bg-red-600 hover:bg-red-700 text-white'
        : 'bg-brand-600 hover:bg-brand-700 text-white';

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 p-4"
            onClick={onCancel}
            role="dialog"
            aria-modal="true"
        >
            <div
                onClick={(e) => e.stopPropagation()}
                className="bg-white border border-slate-200 rounded-lg shadow-lg w-full max-w-sm p-5"
            >
                <h2 className="text-base font-medium text-slate-900 mb-2">{title}</h2>
                <p className="text-sm text-slate-600 mb-5">{message}</p>
                <div className="flex gap-2">
                    <button
                        type="button"
                        onClick={onCancel}
                        disabled={isProcessing}
                        className="flex-1 py-2 text-sm bg-white text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
                    >
                        {cancelLabel}
                    </button>
                    <button
                        type="button"
                        onClick={onConfirm}
                        disabled={isProcessing}
                        className={`flex-1 py-2 text-sm rounded-lg font-medium disabled:opacity-60 ${confirmClasses}`}
                    >
                        {isProcessing ? 'Working…' : confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}