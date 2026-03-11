import axios from 'axios';

const trimTrailingSlash = (value) => value.replace(/\/+$/, '');

export const API_BASE = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || '/api');

export const api = axios.create({
    baseURL: API_BASE,
    withCredentials: true,
});

export const apiUrl = (path = '') => {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${API_BASE}${normalizedPath}`;
};
