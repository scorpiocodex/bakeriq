/* eslint-disable react/react-in-jsx-scope */
/**
 * Approvals page — review registrations submitted through the WhatsApp
 * webform and either promote them to real Customers or reject them.
 *
 * Deliberately card-based rather than a table (unlike Customers). The
 * owner reaches this page by tapping a CTA button in a WhatsApp
 * notification on their phone, so mobile is the primary viewport here.
 * Cards stack cleanly on a narrow screen; a table would need horizontal
 * scrolling or column hiding to fit.
 *
 * Each card shows everything needed to make the decision — name, phone,
 * full address, and how long the request has been waiting — so the owner
 * never has to open a detail view before approving.
 */
import { useState } from 'react';
import { Check, X } from 'lucide-react';

import {
  useApprovalsList,
  useApproveRegistration,
  useRejectRegistration,
} from '../hooks/useApprovals';
import { formatPhone } from '../lib/format';

// =============================================================================
// Helpers
// =============================================================================

// Initials for the avatar circle — same treatment as the customers table.
function getInitials(name) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// "3 hours ago" style relative time. The owner cares about how long
// someone has been waiting far more than the exact timestamp, and a
// long wait is the cue to prioritise.
function timeAgo(isoString) {
  if (!isoString) return '';
  const then = new Date(isoString).getTime();
  const seconds = Math.floor((Date.now() - then) / 1000);

  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

// Join the address parts that are actually present. All five fields are
// optional on the backend, so any of them can be null.
function formatAddress(reg) {
  const parts = [reg.address_line_1, reg.address_line_2, reg.city, reg.state, reg.pincode].filter(
    Boolean,
  );
  return parts.length > 0 ? parts.join(', ') : null;
}

// =============================================================================
// Reject modal — ConfirmDialog doesn't take a text input, and the reason
// field is the whole point here, so this is a small local modal instead.
// =============================================================================

function RejectModal({ open, registration, isProcessing, onConfirm, onCancel }) {
  const [reason, setReason] = useState('');

  if (!open || !registration) return null;

  function handleConfirm() {
    onConfirm(reason.trim() || null);
    setReason('');
  }

  function handleCancel() {
    setReason('');
    onCancel();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={handleCancel} aria-hidden="true" />
      <div className="relative bg-white rounded-lg shadow-lg border border-slate-200 w-full max-w-sm p-4">
        <p className="text-sm font-medium text-slate-900">Reject registration?</p>
        <p className="text-xs text-slate-600 mt-1.5">
          {registration.name} ({formatPhone(registration.phone)}) won&apos;t be able to place
          orders. The request stays on record and they can be told to contact the bakery directly.
        </p>

        <label
          htmlFor="reject-reason"
          className="block text-xs font-medium text-slate-700 mt-3 mb-1"
        >
          Reason <span className="text-slate-400">(optional, for your records)</span>
        </label>
        <textarea
          id="reject-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          maxLength={500}
          placeholder="e.g. duplicate request, not a real customer"
          className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
        />

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={handleCancel}
            disabled={isProcessing}
            className="text-xs px-3 py-1.5 border border-slate-300 text-slate-700 rounded-md hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isProcessing}
            className="text-xs px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-md font-medium disabled:opacity-50"
          >
            {isProcessing ? 'Rejecting…' : 'Reject'}
          </button>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// The page
// =============================================================================

export default function Approvals() {
  const [rejectTarget, setRejectTarget] = useState(null);
  // Tracks which specific card is mid-approve so only that card's button
  // shows a spinner — a shared isPending would grey out every button.
  const [approvingId, setApprovingId] = useState(null);
  const [actionError, setActionError] = useState(null);

  const { data, isLoading, isError, error } = useApprovalsList();
  const approveMut = useApproveRegistration();
  const rejectMut = useRejectRegistration();

  const registrations = data?.items ?? [];
  const total = data?.total ?? 0;

  async function handleApprove(reg) {
    setActionError(null);
    setApprovingId(reg.id);
    try {
      await approveMut.mutateAsync(reg.id);
    } catch (err) {
      // 409 means someone (or a double-tap) already actioned this row.
      // The list invalidation on the other request will drop it shortly.
      setActionError(
        err?.response?.data?.detail ?? `Could not approve ${reg.name}. Please try again.`,
      );
    } finally {
      setApprovingId(null);
    }
  }

  async function handleRejectConfirm(reason) {
    if (!rejectTarget) return;
    setActionError(null);
    try {
      await rejectMut.mutateAsync({ id: rejectTarget.id, reason });
      setRejectTarget(null);
    } catch (err) {
      setActionError(
        err?.response?.data?.detail ?? `Could not reject ${rejectTarget.name}. Please try again.`,
      );
      setRejectTarget(null);
    }
  }

  return (
    <>
      {/* === Page header strip === */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-medium text-slate-900">Approvals</p>
          <p className="text-xs text-slate-500">
            {isLoading
              ? 'Loading…'
              : total === 0
                ? 'No registrations waiting'
                : `${total} registration${total === 1 ? '' : 's'} awaiting review`}
          </p>
        </div>
      </div>

      {/* === Action error banner === */}
      {actionError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-2.5">
          <p className="text-xs text-red-700">{actionError}</p>
        </div>
      )}

      {/* === Loading / error / empty states === */}
      {isLoading && (
        <div className="bg-white border border-slate-200 rounded-lg px-3 py-8">
          <p className="text-xs text-center text-slate-500">Loading registrations…</p>
        </div>
      )}

      {isError && (
        <div className="bg-white border border-slate-200 rounded-lg px-3 py-8">
          <p className="text-xs text-center text-red-700">
            Could not load registrations: {error?.message ?? 'unknown error'}
          </p>
        </div>
      )}

      {!isLoading && !isError && registrations.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-lg px-3 py-10">
          <p className="text-xs text-center text-slate-500">Nothing to review right now.</p>
          <p className="text-[11px] text-center text-slate-400 mt-1">
            New registrations from WhatsApp will appear here.
          </p>
        </div>
      )}

      {/* === Registration cards === */}
      <div className="space-y-2.5">
        {registrations.map((reg) => {
          const address = formatAddress(reg);
          const isApproving = approvingId === reg.id;

          return (
            <div key={reg.id} className="bg-white border border-slate-200 rounded-lg p-3">
              {/* Identity row */}
              <div className="flex items-start gap-2.5">
                <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-800 text-[11px] font-medium flex items-center justify-center flex-shrink-0">
                  {getInitials(reg.name)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900 truncate">{reg.name}</p>
                  <p className="font-mono text-[11px] text-slate-600">{formatPhone(reg.phone)}</p>
                </div>
                <span className="text-[10px] text-slate-400 flex-shrink-0 whitespace-nowrap">
                  {timeAgo(reg.created_at)}
                </span>
              </div>

              {/* Address block — only rendered when something was supplied,
                  since every address field is optional on the webform. */}
              {address && (
                <div className="mt-2.5 pl-[42px]">
                  <p className="text-[10px] uppercase tracking-wider text-slate-400 font-medium mb-0.5">
                    Delivery address
                  </p>
                  <p className="text-xs text-slate-700 leading-snug">{address}</p>
                </div>
              )}

              {/* Actions — full-width split buttons, comfortable tap targets
                  since this page is mostly used on a phone. */}
              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => setRejectTarget(reg)}
                  disabled={isApproving || rejectMut.isPending}
                  className="flex-1 flex items-center justify-center gap-1.5 text-xs px-3 py-2 border border-slate-300 text-slate-700 rounded-md hover:bg-slate-50 disabled:opacity-50"
                >
                  <X size={14} aria-hidden="true" />
                  Reject
                </button>
                <button
                  onClick={() => handleApprove(reg)}
                  disabled={isApproving || rejectMut.isPending}
                  className="flex-1 flex items-center justify-center gap-1.5 text-xs px-3 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium disabled:opacity-50"
                >
                  <Check size={14} aria-hidden="true" />
                  {isApproving ? 'Approving…' : 'Approve'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* === Reject modal === */}
      <RejectModal
        open={rejectTarget !== null}
        registration={rejectTarget}
        isProcessing={rejectMut.isPending}
        onConfirm={handleRejectConfirm}
        onCancel={() => setRejectTarget(null)}
      />
    </>
  );
}
