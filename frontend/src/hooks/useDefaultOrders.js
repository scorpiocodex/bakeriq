/**
 * TanStack Query hooks for default orders (customer-scoped).
 *
 * The notable wrinkle: a 404 from getDefaultOrder is a NORMAL state — it
 * means "this customer has no template yet," not an error. We special-case
 * it so the UI shows an empty editor rather than an error banner.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    deleteDefaultOrder,
    getDefaultOrder,
    upsertDefaultOrder,
} from '../api/defaultOrders';

// === Query ==================================================================

/**
 * Fetch a customer's default order template.
 *
 * Returns the standard TanStack result, but with 404 handled specially:
 *   - .data === null  → customer has no template yet (show empty editor)
 *   - .data === {...}  → the template
 *
 * We map a 404 to null inside queryFn rather than letting it become an
 * error, because "no template" is an expected, non-error state. Other
 * errors (500, network) still propagate as .isError.
 *
 * enabled: only fires when a customerId is provided AND the modal is open
 * (the caller passes enabled to avoid fetching for every customer row).
 */
export function useDefaultOrder(customerId, { enabled = true } = {}) {
    return useQuery({
        queryKey: ['defaultOrders', customerId],
        queryFn: async () => {
            try {
                return await getDefaultOrder(customerId);
            } catch (err) {
                if (err.response?.status === 404) {
                    return null; // no template yet — not an error
                }
                throw err; // real error — let TanStack surface it
            }
        },
        enabled: Boolean(customerId) && enabled,
    });
}

// === Mutations ==============================================================

/**
 * Create or replace a customer's template.
 *
 * Invalidates the specific customer's default-order query so the editor
 * refreshes with the saved state.
 */
export function useUpsertDefaultOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ customerId, payload }) =>
            upsertDefaultOrder(customerId, payload),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({
                queryKey: ['defaultOrders', variables.customerId],
            });
        },
    });
}

/**
 * Delete a customer's template entirely.
 */
export function useDeleteDefaultOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (customerId) => deleteDefaultOrder(customerId),
        onSuccess: (_data, customerId) => {
            queryClient.invalidateQueries({
                queryKey: ['defaultOrders', customerId],
            });
        },
    });
}