export interface UserInfo {
  id: number;
  username: string;
  email: string | null;
  role: 'superadmin' | 'admin' | 'teacher' | 'student' | 'parent';
  school_id: number | null;
  student_id: number | null;
  is_verified: boolean;
}

export interface SchoolInfo {
  id: number;
  name: string;
  subdomain: string;
  email: string;
  phone: string | null;
  address: string | null;
  plan: 'free' | 'starter' | 'growth' | 'enterprise';
  billing_cycle: 'monthly' | 'yearly';
  is_active: boolean;
  on_trial: boolean;
  subscription_active: boolean;
  trial_ends_at: string | null;
  subscription_ends_at: string | null;
}

export interface BootstrapPayload {
  authenticated: boolean;
  csrf_token: string;
  user: UserInfo | null;
  school: SchoolInfo | null;
  schools: Array<{ id: number; name: string; subdomain: string }>;
  unread_notifications: number;
  pricing: {
    prices: Record<string, { name: string; amount_monthly: number; amount_yearly: number; currency: string }>;
    limits: Record<string, { students: number | null; teachers: number | null }>;
    features: Record<string, string[]>;
    simulator_enabled: boolean;
  };
}

export class ApiError extends Error {
  status: number;
  subscriptionExpired?: boolean;

  constructor(message: string, status: number, subscriptionExpired = false) {
    super(message);
    this.status = status;
    this.subscriptionExpired = subscriptionExpired;
  }
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: 'include',
  });

  let payload: any = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    payload = await response.json();
  } else {
    const text = await response.text();
    payload = { message: text };
  }

  if (!response.ok) {
    throw new ApiError(
      payload?.error || payload?.message || `Request failed (${response.status})`,
      response.status,
      Boolean(payload?.subscription_expired)
    );
  }

  return payload as T;
}
