/**
 * React Query hooks for customer data.
 *
 * Why hooks separate from api/customers.js:
 *   - api/ files are pure functions (no React, testable in isolation)
 *   - hooks/ are React-specific (use useQuery/useMutation, only callable from components)
 *   This split means non-React code (e.g. a future Node.js script) could
 *   reuse api/customers.js. It's also a clean separation of concerns.
 *
 * Components should ALWAYS use these hooks rather than calling
 * api/customers.js directly. The hooks add caching, automatic refetching,
 * and consistent invalidation that components shouldn't have to think about.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    createCustomer,
    deactivateCustomer,
    getCustomer,
    listCustomers,
    updateCustomer,
} from '../api/customers';

// =============================================================================
// Query keys — centralised so cache invalidation always uses matching keys.
// =============================================================================
//
// Mistyping a key elsewhere is the most common cause of "why isn't my list
// refreshing after I created a new row?" bugs. Defining keys here once
// eliminates that class of bug entirely.
//
// Hierarchical structure lets us invalidate at different granularities:
//   customerKeys.all              — invalidates EVERYTHING customer-related
//   customerKeys.lists()          — invalidates ALL lists (any filter combo)
//   customerKeys.list(filters)    — invalidates ONE specific list
//   customerKeys.detail(id)       — invalidates ONE specific customer
//
export const customerKeys = {
    all: ['customers'],
    lists: () => [...customerKeys.all, 'list'],
    list: (filters) => [...customerKeys.lists(), filters],
    detail: (id) => [...customerKeys.all, 'detail', id],
};

// =============================================================================
// Queries (read operations)
// =============================================================================

/**
 * Hook for the customers list page.
 *
 * filters = { search, whatsappOnly, includeInactive, skip, limit }
 *
 * placeholderData: (previousData) => previousData
 *   When filters change, the OLD list stays visible until the new data
 *   arrives. Without this, every keystroke in the search box would flash
 *   the list to "Loading..." for 200ms. With it, the user sees the
 *   previous results faded slightly until the new query resolves —
 *   much smoother UX.
 *
 * Returns: { data, isLoading, isError, error, isFetching, refetch }
 *   - data: { items, total, skip, limit } (or undefined while loading)
 *   - isLoading: true ONLY on first load (no previous data)
 *   - isFetching: true ANY time a request is in-flight (incl. background refresh)
 *   - isError + error: query failure
 *   - refetch: manual trigger
 */
export function useCustomersList(filters = {}) {
    return useQuery({
        queryKey: customerKeys.list(filters),
        queryFn: () => listCustomers(filters),
        placeholderData: (previousData) => previousData,
    });
}

/**
 * Hook for a single customer (used in detail views, edit modal pre-fill).
 *
 * enabled: Boolean(customerId)
 *   Skip running the query if customerId is null/undefined. Used in the
 *   form modal, which mounts before any customer is selected for editing.
 */
export function useCustomer(customerId) {
    return useQuery({
        queryKey: customerKeys.detail(customerId),
        queryFn: () => getCustomer(customerId),
        enabled: Boolean(customerId),
    });
}

// =============================================================================
// Mutations (write operations)
// =============================================================================
//
// After a successful mutation, the data on the server has changed but our
// cache is stale. We have two options:
//
//   A) invalidateQueries — marks matching cache entries dirty. Next time
//      a hook with that key is observed, it refetches. Safer (always gets
//      fresh data from server), one extra request per mutation.
//
//   B) setQueryData — directly write the new data into the cache without
//      a server round-trip. Fast, but only correct when you're SURE the
//      response represents the final server state.
//
// Pattern below: invalidate lists (because the server might apply ordering
// changes we haven't computed locally), but setQueryData for individual
// detail caches (the response IS the new server state).

/**
 * Mutation: create.
 *
 * On success, invalidate all list caches so the new customer appears
 * immediately in any list view that's currently mounted.
 */
export function useCreateCustomer() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: createCustomer,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: customerKeys.lists() });
        },
    });
}

/**
 * Mutation: update.
 *
 * Takes { id, payload } as a single argument because useMutation's
 * mutationFn takes exactly ONE argument. We unpack it inside.
 *
 * On success: invalidate lists AND set the detail cache to the response.
 * setQueryData skips an unnecessary refetch of the detail.
 */
export function useUpdateCustomer() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }) => updateCustomer(id, payload),
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: customerKeys.lists() });
            queryClient.setQueryData(customerKeys.detail(data.id), data);
        },
    });
}

/**
 * Mutation: deactivate (soft delete).
 *
 * Same pattern as update — invalidate lists so the deactivated row
 * disappears from active filters, set detail to the new (inactive) state.
 */
export function useDeactivateCustomer() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: deactivateCustomer,
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: customerKeys.lists() });
            queryClient.setQueryData(customerKeys.detail(data.id), data);
        },
    });
}