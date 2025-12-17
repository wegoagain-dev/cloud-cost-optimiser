import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
});

export const getDashboardStats = async () => {
  const response = await api.get('/api/dashboard/stats');
  return response.data;
};

export const getLatestFindings = async () => {
  const response = await api.get('/api/findings/latest');
  return response.data;
};

export const triggerScan = async (region = 'eu-west-2') => {
  const response = await api.post('/api/scans/run', {
    region,
    save_to_db: true
  });
  return response.data;
};

export const getScan = async (scanId) => {
  const response = await api.get(`/api/scans/${scanId}`);
  return response.data;
};

export default api;
