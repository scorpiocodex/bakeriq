import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createCategory, deactivateCategory, getCategory, hardDeleteCategory, listCategories, updateCategory } from '../api/categories';


export function useCategoriesList(filters = {}) {
    return useQuery({
        queryKey: ['categories', 'list', filters],
        queryFn: () => listCategories(filters),
        keepPreviousData: true,
    });
}


export function useCategory(id) {
    return useQuery({
        queryKey: ['categories', 'detail', id],
        queryFn: () => getCategory(id),
        enabled: Boolean(id),
    });
}


export function useCreateCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload) => createCategory(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['categories'] });
        },
    });
}


export function useUpdateCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }) => updateCategory(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['categories'] });
            queryClient.invalidateQueries({ queryKey: ['products'] });
        },
    });
}


export function useDeactivateCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id) => deactivateCategory(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['categories'] });
            queryClient.invalidateQueries({ queryKey: ['products'] });
        },
    });
}


export function useHardDeleteCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id) => hardDeleteCategory(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['categories'] });
        },
    });
}