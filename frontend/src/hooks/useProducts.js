import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    createProduct,
    deactivateProduct,
    getProduct,
    listProducts,
    updateProduct,
} from '../api/products';


export function useProductsList(filters = {}) {
    return useQuery({
        queryKey: ['products', 'list', filters],
        queryFn: () => listProducts(filters),
        keepPreviousData: true,
    });
}


export function useProduct(id) {
    return useQuery({
        queryKey: ['products', 'detail', id],
        queryFn: () => getProduct(id),
        enabled: Boolean(id),
    });
}


export function useCreateProduct() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload) => createProduct(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['products'] });
        },
    });
}


export function useUpdateProduct() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }) => updateProduct(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['products'] });
        },
    });
}


export function useDeactivateProduct() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id) => deactivateProduct(id),
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: ['products']
            })
        },
    });
}