/**
 * services/api.js
 * Central Axios instance. Automatically:
 * * - Attaches JWT access token to every request
 * * - Refreshes the token on 401 and retries once
 * * - Redirects to login on refresh failure
 * */
import axios from "axios";
import * as SecureStore from "expo-secure-store";

// ── Change this to your Flask server URL ───────────────────────
export const BASE_URL = "https://api.yoursaas.com/api/v1";
// For local dev:  "http://192.168.x.x:5000/api/v1"

const api = axios.create({
	baseURL: BASE_URL,
	timeout: 15000,
	headers: { "Content-Type": "application/json" },
});    


//── Request interceptor: attach access token ───────────────────
api.interceptors.request.use(async (config) => {
	const token = await SecureStore.getItemAsync("access_token");
	if (token) config.headers.Authorization = `Bearer ${token}`;
	return config;
});

// ── Response interceptor: handle 401, refresh token ───────────
let isRefreshing = false;
let failedQueue  = [];

const processQueue = (error, token = null) => {
	failedQueue.forEach((prom) => {
		if (error) prom.reject(error);
		else prom.resolve(token);
	});
	failedQueue = [];
};

api.interceptors.response.use(
	(response) => response,
	async (error) => {
		const originalRequest = error.config;
		   
		if (error.response?.status === 401 && !originalRequest._retry) {
			if (isRefreshing) {
				return new Promise((resolve, reject) => {
					failedQueue.push({ resolve, reject });
				})
					.then((token) => {
						originalRequest.headers.Authorization = `Bearer ${token}`;
						return api(originalRequest);
					})
					.catch((err) => Promise.reject(err));
			}

			originalRequest._retry = true;
			isRefreshing = true;
			 
			try {
				const refreshToken = await SecureStore.getItemAsync("refresh_token");
				const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {}, {
					headers: { Authorization: `Bearer ${refreshToken}` },
				});

				await SecureStore.setItemAsync("access_token", data.access_token);
				api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
				processQueue(null, data.access_token);
				return api(originalRequest);
			} catch (refreshError) {
				processQueue(refreshError, null);
				// Clear tokens and force re-login
				await SecureStore.deleteItemAsync("access_token");
				await SecureStore.deleteItemAsync("refresh_token");
				// useAuthStore handles navigation
				useAuthStore.getState().logout();
				return Promise.reject(refreshError);
			} finally {
				isRefreshing = false;
			}
		}
		
		return Promise.reject(error);
	}
);

export default api;

// ── Auth endpoints ─────────────────────────────────────────────
export const authAPI = {
	login:          (data) => api.post("/auth/login", data),
	logout:         ()     => api.post("/auth/logout"),
	refresh:        ()     => api.post("/auth/refresh"),
	me:             ()     => api.get("/auth/me"),
	changePassword: (data) => api.post("/auth/change-password", data),
};

// ── Dashboard endpoints ────────────────────────────────────────
export const dashboardAPI = {
	admin:   () => api.get("/dashboard/admin"),
	student: () => api.get("/dashboard/student"),
	teacher: () => api.get("/dashboard/teacher"),
};

// ── Student endpoints ──────────────────────────────────────────
export const studentsAPI = {
	list:       (params)     => api.get("/students", { params }),
	get:        (id)         => api.get(`/students/${id}`),
	me:         ()           => api.get("/students/me"),
	create:     (data)       => api.post("/students", data),
	results:    (id)         => api.get(`/students/${id}/results`),
	attendance: (id)         => api.get(`/students/${id}/attendance`),
	fees:       (id)         => api.get(`/students/${id}/fees`),
};

// ── Attendance endpoints ───────────────────────────────────────
export const attendanceAPI = {
	get:  (params) => api.get("/attendance", { params }),
	bulk: (data)   => api.post("/attendance/bulk", data),
};

// ── Results endpoints ──────────────────────────────────────────
export const resultsAPI = {
	bulk: (data) => api.post("/results/bulk", data),
};

// ── Fee endpoints ──────────────────────────────────────────────
export const feesAPI = {
	structures: ()     => api.get("/fees/structures"),
	payments:   (p)    => api.get("/fees/payments", { params: p }),
	pay:        (data) => api.post("/fees/pay", data),
};

// ── Notification endpoints ─────────────────────────────────────
export const notificationsAPI = {
	list:      ()   => api.get("/notifications"),
	markRead:  (id) => api.patch(`/notifications/${id}/read`),
	markAll:   ()   => api.patch("/notifications/read-all"),
};

// ── Reference data endpoints ───────────────────────────────────
export const schoolAPI = {
	classes:       () => api.get("/classes"),
	subjects:      () => api.get("/subjects"),
	terms:         () => api.get("/terms"),
	exams:         () => api.get("/exams"),
	teachers:      () => api.get("/teachers"),
	announcements: () => api.get("/announcements"),
	analytics:     () => api.get("/analytics"),
};
