import client from './client';

// POST /auth/login
// FastAPI's OAuth2PasswordRequestForm expects FORM-DATA
// (application/x-www-form-urlencoded), NOT JSON. This is mandated by the
// OAuth2 password flow spec and is what the Swagger UI 'Authorize' button
// also sends. Pass JSON here and you get HTTP 422 immediately.
export async function login(email, password) {
    const params = new URLSearchParams();
    params.append('username', email);  // FastAPI calls the field 'username'
    params.append('password', password);

    const { data } = await client.post('/auth/login', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    // data: { access_token: "eyJ...", token_type: "bearer" }
    return data;
}

// POST /auth/register — admin operation in Phase 1.
export async function register({ email, password, full_name }) {
    const { data } = await client.post('/auth/register', {
        email,
        password,
        full_name,
    });
    return data;
}

// GET /auth/me — used to bootstrap the session on page load.
// If the token in localStorage is still valid, this returns the user;
// if not, the response interceptor in client.js handles the 401 cleanup.
export async function getMe() {
    const { data } = await client.get('/auth/me');
    return data;
}

// Synchronous "logout" — just clears local state. No server call needed
// because JWTs are stateless. If we later add a server-side blocklist
// for revoked tokens, we'd POST to /auth/logout here.
export function logout() {
    localStorage.removeItem('bakeriq_token');
    window.location.href = '/login';
}