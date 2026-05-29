/**
 * API client for the dashboard summary.
 *
 * Single read-only endpoint — today's order-flow snapshot plus reference
 * counts. No parameters; the server reports "today" by order_date.
 */

import client from './client';

/**
 * GET /dashboard/summary
 *
 * Returns {
 *   today_orders, pending, in_progress, cancelled_today, revenue_today,
 *   board: { received:[], preparing:[], ready:[], delivering:[] },
 *   active_customers, active_products, unavailable_products, summary_date
 * }
 */

export async function getDashboardSummary() {
    const { data } = await client.get('/dashboard/summary');
    return data;
}