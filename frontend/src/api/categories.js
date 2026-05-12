import client from './client';

export async function listCategories({
    skip = 0,
    limit = 100,
    status = 'active',
} = {}) {
    const params = { skip, limit, status };
    const { data } = await client.get('/categories', { params });
    return data;
}

export function getCategory(id) {
    const { data } = await client.get(`/categories/${id}`);
    return data;
}

export async function createCategory(payload) {
    const { data } = await client.post('/categories', payload);
    return data;
}

export async function updateCategory(id, payload) {
    const { data } = await client.put(`/categories/${id}`, payload);
    return data;
}

export async function deactivateCategory(id) {
    const { data } = await client.delete(`/categories/${id}`);
    return data;
}

export async function hardDeleteCategory(id) {
    await client.delete(`/categories/${id}/hard`);
    // 204 No Content — nothing to return
}

