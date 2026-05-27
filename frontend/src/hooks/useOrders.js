/**
 * TanStack Query hooks for orders.
 *
 * Query keys:
 *   ['orders', 'list', filters]  — the list view
 *   ['orders', 'detail', id]     — a single order's full detail
 *
 * Mutations invalidate ['orders'] so both list and any open detail refresh.
 * Status changes and edits both touch the same order, so both invalidate
 * the detail key for that id as well as the list.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    changeOrderStatus,
    createOrder,
    deleteOrder,
    getOrder,
    getOrderPrefill,
    listOrders,
    updateOrder,
} from '../api/orders';

// === Queries ================================================================

/**
 * Paginated, filterable list of compact order rows.
 * filters: { skip, limit, status, customerId, orderDate }
 */
export function useOrdersList(filters = {}) {
    return useQuery({
        queryKey: ['orders', 'list', filters],
        queryFn: () => listOrders(filters),
        keepPreviousData: true,
    });
}

/**
 * Full detail for one order (with line items). Enabled only when an id is
 * provided — so the detail panel can mount with no selection and not fetch.
 */
export function useOrder(id, { enabled = true } = {}) {
    return useQuery({
        queryKey: ['orders', 'detail', id],
        queryFn: () => getOrder(id),
        enabled: Boolean(id) && enabled,
    });
}

// === Mutations ==============================================================

export function useCreateOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload) => createOrder(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['orders'] });
        },
    });
}

export function useUpdateOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }) => updateOrder(id, payload),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['orders'] });
            queryClient.invalidateQueries({
                queryKey: ['orders', 'detail', variables.id],
            });
        },
    });
}

export function useChangeOrderStatus() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, status }) => changeOrderStatus(id, status),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['orders'] });
            queryClient.invalidateQueries({
                queryKey: ['orders', 'detail', variables.id],
            });
        },
    });
}

export function useDeleteOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id) => deleteOrder(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['orders'] });
        },
    });
}

// === Prefill (read-only helper) =============================================

/**
 * Fetch suggested order lines from a customer's default template.
 *
 * NOT a hook with caching by customer in the usual sense — it's invoked
 * on demand (when the user clicks "Load default order"), so we expose it
 * as a mutation-style trigger rather than a passive query. Using useMutation
 * gives us mutateAsync to call imperatively and get the result back.
 */
export function useOrderPrefill() {
    return useMutation({
        mutationFn: (customerId) => getOrderPrefill(customerId),
    });
}