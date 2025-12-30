import axios from 'axios';

// Production should never call localhost from the deployed site.
// Prefer VITE_API_URL injected at build time; otherwise fall back to the known Azure backend FQDN.
const DEFAULT_PROD_API_URL = 'https://backend.mangoocean-d0c97d4f.westus2.azurecontainerapps.io';
const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? DEFAULT_PROD_API_URL : 'http://localhost:8000');

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

export default api;
