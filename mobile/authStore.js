/**
 * store/authStore.js
 * Global auth state using Zustand.
 * Stores user, tokens, and school info.
 */
import { create } from "zustand";
import * as SecureStore from "expo-secure-store";
import { authAPI } from "../services/api";

const useAuthStore = create((set, get) => ({
	user:         null,
	school:       null,
	isLoading:    true,
	isLoggedIn:   false,

	// ── Restore session on app launch ────────────────────────────
	restoreSession: async () => {
		try {
			const token = await SecureStore.getItemAsync("access_token");
			if (!token) {
				set({ isLoading: false, isLoggedIn: false });
				return;
			}
			const { data } = await authAPI.me();
			set({
				user:       data,
				school:     data.school,
				isLoggedIn: true,
				isLoading:  false,
			});
		} catch {
			await SecureStore.deleteItemAsync("access_token");
			await SecureStore.deleteItemAsync("refresh_token");
			set({ isLoading: false, isLoggedIn: false });
		}
	},

	// ── Login ─────────────────────────────────────────────────────
	login: async ({ subdomain, username, password }) => {
		const { data } = await authAPI.login({ subdomain, username, password });
		await SecureStore.setItemAsync("access_token",  data.access_token);
		await SecureStore.setItemAsync("refresh_token", data.refresh_token);
		set({ user: data.user, school: data.user.school, isLoggedIn: true });
	        return data.user;
	},

	// ── Logout ────────────────────────────────────────────────────
	logout: async () => {
		try { await authAPI.logout(); } catch {}
		await SecureStore.deleteItemAsync("access_token");
		await SecureStore.deleteItemAsync("refresh_token");
		set({ user: null, school: null, isLoggedIn: false });
	},

	// ── Helpers ───────────────────────────────────────────────────
	getRole:    () => get().user?.role,
	getSchool:  () => get().school,
	isAdmin:    () => get().user?.role === "admin",
	isTeacher:  () => get().user?.role === "teacher",
	isStudent:  () => get().user?.role === "student",
	isParent:   () => get().user?.role === "parent",
}));
 
export default useAuthStore;
