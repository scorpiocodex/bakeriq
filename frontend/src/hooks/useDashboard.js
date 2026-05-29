/**
 * TanStack Query hook for the dashboard summary.
 *
 * Short staleTime so the dashboard feels live without hammering the API —
 * the board reflects order/status changes within a reasonable window, and
 * any mutation elsewhere (creating an order, changing status) already
 * invalidates ['orders'], but the dashboard has its own key so we also
 * refetch on window focus to stay current.
 */

import { useQuery } from '@tanstack/react-query';
import { getDashboardSummary } from '../api/dashboard';

export function useDashboardSummary() {
    return useQuery({
        queryKey: ['dashboard', 'summary'],
        queryFn: getDashboardSummary,
        staleTime: 30_000,          // 30s
        refetchOnWindowFocus: true, // re-pull
    });
}