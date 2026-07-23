/**
 * React Query hooks for inventory.
 *
 * Mutations here can invalidate two resources. Changing a count only
 * touches stock; toggling tracking also changes the product row, so any
 * mounted product list is stale too.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPrepList, listStock, setStock, updateStockSettings } from '../api/inventory';

export const inventoryKeys = {
  all: ['inventory'],
  stock: (filters) => [...inventoryKeys.all, 'stock', filters],
  prep: () => [...inventoryKeys.all, 'prep'],
};

export function useStockList(filters = {}) {
  return useQuery({
    queryKey: inventoryKeys.stock(filters),
    queryFn: () => listStock(filters),
    // Keep the old rows visible while a filter change loads, rather
    // than flashing the table to empty.
    placeholderData: (previousData) => previousData,
  });
}

export function usePrepList() {
  return useQuery({
    queryKey: inventoryKeys.prep(),
    queryFn: getPrepList,
    // The window opens at 5 AM and closes at 9 PM. A dashboard left
    // open overnight should notice without a manual reload.
    refetchInterval: 5 * 60 * 1000,
  });
}

export function useSetStock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, quantity }) => setStock(id, quantity),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.all });
    },
  });
}

export function useUpdateStockSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => updateStockSettings(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.all });
      // is_stockable lives on the product, so product lists are stale.
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
  });
}
