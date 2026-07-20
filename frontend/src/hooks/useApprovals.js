/**
 * React Query hooks for the pending-registration approvals queue.
 *
 * Same split as useCustomers.js: api/approvals.js holds pure functions,
 * this file wraps them in React Query so components get caching and
 * consistent invalidation for free.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  approveRegistration,
  getApprovalsCount,
  listApprovals,
  rejectRegistration,
} from '../api/approvals';

// =============================================================================
// Query keys
// =============================================================================
//
// Two independent reads — the full list (approvals page) and the bare count
// (sidebar badge). They're siblings under `all` so a single mutation can
// invalidate both with one call to approvalKeys.all.
//
export const approvalKeys = {
  all: ['approvals'],
  list: () => [...approvalKeys.all, 'list'],
  count: () => [...approvalKeys.all, 'count'],
};

// =============================================================================
// Queries
// =============================================================================

/**
 * Hook for the approvals page list.
 *
 * Returns { data: { items, total }, isLoading, isError, error, ... }
 */
export function useApprovalsList() {
  return useQuery({
    queryKey: approvalKeys.list(),
    queryFn: listApprovals,
  });
}

/**
 * Hook for the sidebar badge count.
 *
 * refetchInterval: 30_000
 *   The owner needs to notice a new registration without reloading the
 *   page. 30s is a deliberate middle ground — fast enough that the badge
 *   feels live, slow enough that an idle dashboard isn't hammering the
 *   API all day. WebSockets would be lower-latency but are a lot of
 *   moving parts for a signal that arrives a few times a day.
 *
 * refetchOnWindowFocus is on by default in React Query, which covers the
 * common case of the owner tabbing back after reading the WhatsApp card.
 */
export function useApprovalsCount() {
  return useQuery({
    queryKey: approvalKeys.count(),
    queryFn: getApprovalsCount,
    refetchInterval: 30_000,
  });
}

// =============================================================================
// Mutations
// =============================================================================
//
// Both mutations invalidate approvalKeys.all — the approved/rejected row
// leaves the list AND the badge count drops, so both reads are stale.
//
// Approve also invalidates the customers list, because approving creates a
// real Customer row that should appear on /customers immediately.

/**
 * Mutation: approve a registration (creates a Customer).
 */
export function useApproveRegistration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: approveRegistration,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all });
      // A new Customer now exists — any mounted customer list is stale.
      queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
  });
}

/**
 * Mutation: reject a registration.
 *
 * Takes { id, reason } as one argument because mutationFn accepts exactly
 * one. reason may be null.
 */
export function useRejectRegistration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }) => rejectRegistration(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all });
    },
  });
}
