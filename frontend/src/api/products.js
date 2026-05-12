import client from 'client';

export async function listProducts({
    skip = 0,
    limit = 50,
    search = null,
    categoryId = null,
    status = 'active',
    availableToday = null,
} = {}) {
    const params = {
        skip,
        limit,
        search,
    };
    if (search) params.search = search;
    if (categoryId) params.category_id = categoryId;
    if (availableToday !== null) params.available_today = availableToday;

    const { data } = await client.get('/products', { params });
    return data;
}

export async function getProduct(id) {
    const { data } = await client.get(`/products/${id}`);
    return data;
}

export async function createProduct(payload) {
    const { data } = await client.post('/products', payload);
    return data;
}

export async function updateProduct(id, payload) {
    const { data } = await client.put(`/products/${id}`, payload);
    return data;
}

export async function deactivateProduct(id) {
    const { data } = await client.delete(`/products/${id}`);
    return data;
}