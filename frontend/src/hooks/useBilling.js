/**
 * React Query hooks for billing.
 *
 * Billing is read-only, so there are no mutations and nothing to
 * invalidate. Keys carry the date range because changing the range is a
 * different query, not a refetch of the same one.
 */
import { useQuery } from '@tanstack/react-query';
import {
  getBillingSummary,
  getInvoice,
  listBillingCustomers,
  listCustomerInvoiceDates,
} from '../api/billing';

export const billingKeys = {
  all: ['billing'],
  summary: (range) => [...billingKeys.all, 'summary', range],
  customers: (range) => [...billingKeys.all, 'customers', range],
  dates: (customerId, range) => [...billingKeys.all, 'dates', customerId, range],
  invoice: (customerId, date) => [...billingKeys.all, 'invoice', customerId, date],
};

export function useBillingSummary(range) {
  return useQuery({
    queryKey: billingKeys.summary(range),
    queryFn: () => getBillingSummary(range),
    // Keep the previous numbers on screen while a new range loads,
    // rather than flashing the cards back to a loading state.
    placeholderData: (previousData) => previousData,
  });
}

export function useBillingCustomers(range) {
  return useQuery({
    queryKey: billingKeys.customers(range),
    queryFn: () => listBillingCustomers(range),
    placeholderData: (previousData) => previousData,
  });
}

export function useCustomerInvoiceDates(customerId, range) {
  return useQuery({
    queryKey: billingKeys.dates(customerId, range),
    queryFn: () => listCustomerInvoiceDates(customerId, range),
    enabled: Boolean(customerId),
  });
}

export function useInvoice(customerId, invoiceDate) {
  return useQuery({
    queryKey: billingKeys.invoice(customerId, invoiceDate),
    queryFn: () => getInvoice(customerId, invoiceDate),
    enabled: Boolean(customerId && invoiceDate),
    // A 404 here means "no invoice that day" — a real answer, not a
    // transient failure. Retrying just delays showing it.
    retry: false,
  });
}
