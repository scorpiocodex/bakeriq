/**
 * Approvals API — pending registration review endpoints.
 *
 * Pure functions, no React. Called by hooks/useApprovals.js.
 *
 * Backend routes (all JWT-authed — client.js attaches the token):
 *   GET  /approvals              list awaiting registrations
 *   GET  /approvals/count        count only (sidebar badge polling)
 *   POST /approvals/{id}/approve creates a Customer from the registration
 *   POST /approvals/{id}/reject  marks rejected, no Customer created
 */
import client from './client';

/**
 * List registrations awaiting owner action, oldest first.
 *
 * Returns { items: [...], total: number }.
 * No pagination params — the awaiting queue is naturally small (0-5 rows
 * in normal operation) and the backend returns all of them.
 */
export async function listApprovals() {
  const { data } = await client.get('/approvals');
  return data;
}

/**
 * Count of awaiting registrations.
 *
 * Separate from listApprovals so the sidebar badge can poll every 30s
 * without dragging back full row data on every tick.
 *
 * Returns { count: number }.
 */
export async function getApprovalsCount() {
  const { data } = await client.get('/approvals/count');
  return data;
}

/**
 * Approve a registration — creates the Customer row.
 *
 * Returns { message, customer_id }.
 * Throws 409 if the registration is already approved or rejected.
 */
export async function approveRegistration(registrationId) {
  const { data } = await client.post(`/approvals/${registrationId}/approve`);
  return data;
}

/**
 * Reject a registration — flips status, keeps the row for audit.
 *
 * reason is optional; pass null or omit for obvious-garbage rejections.
 *
 * Returns { message, registration_id }.
 * Throws 409 if the registration is already approved or rejected.
 */
export async function rejectRegistration(registrationId, reason = null) {
  const { data } = await client.post(`/approvals/${registrationId}/reject`, {
    reason: reason || null,
  });
  return data;
}
