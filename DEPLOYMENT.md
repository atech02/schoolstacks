# EduManage — Firebase Hosting & Cloud Run Deployment Guide

This guide covers deploying **EduManage** (Python Flask + PostgreSQL + Lipila Payments + PWA) to **Firebase Hosting (`https://edumanage-7a46d.web.app`)** backed by **Google Cloud Run** under your Firebase project **`edumanage-7a46d`**.

---

## 1. Architecture Overview

- **Firebase Hosting (`firebase.json`)**:
  - Serves static PWA assets (`/manifest.json`, `/sw.js`, `/static/icons/*`) directly from Firebase's global CDN.
  - Forwards all dynamic application routes (`**` — including `GET` and `POST` requests, authentication, dashboards, and Lipila webhooks) to the `edumanage-backend` Cloud Run service in `us-central1`.
  - **No SPA `index.html` fallback** is used, ensuring `POST` forms and `/billing/webhook/lipila` callbacks reach Flask intact.
- **Multi-Tenant Resolution on `.web.app`**:
  - Schools can be accessed on the shared Firebase domain via **`https://edumanage-7a46d.web.app/s/<school-subdomain>`** (e.g., `https://edumanage-7a46d.web.app/s/stmarys`) or by selecting the school from the dropdown on `/login`.
  - Once authenticated, every query is strictly isolated to `current_user.school_id`.

---

## 2. Prerequisites

1. **Google Cloud & Firebase Project (`edumanage-7a46d`)**:
   - Cloud Run requires the **Blaze (Pay-as-you-go)** plan enabled on your Firebase/Google Cloud project (`edumanage-7a46d`).
2. **CLI Tools Installed**:
   - [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install)
   - [Firebase CLI (`firebase-tools`)](https://firebase.google.com/docs/cli): `npm install -g firebase-tools`
3. **Persistent PostgreSQL Database**:
   - Provision a PostgreSQL database (e.g., **Neon Serverless Postgres**, **Supabase**, or **Google Cloud SQL for PostgreSQL**).
   - Copy your connection string: `postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require`.

---

## 3. Step-by-Step Deployment Commands

### Step 1 — Authenticate CLIs & Select Project
```powershell
gcloud auth login
gcloud config set project edumanage-7a46d

npx firebase-tools login
npx firebase-tools use edumanage-7a46d
```

### Step 2 — Deploy the Flask Backend to Cloud Run
Deploy the container from source to Cloud Run (`us-central1`) with your environment variables:
```powershell
gcloud run deploy edumanage-backend `
  --source . `
  --project edumanage-7a46d `
  --region us-central1 `
  --allow-unauthenticated `
  --set-env-vars "FLASK_ENV=production,APP_PROTOCOL=https,BASE_DOMAIN=edumanage-7a46d.web.app,LIPILA_ENV=sandbox,LIPILA_CURRENCY=ZMW" `
  --set-env-vars "SECRET_KEY=YOUR_STRONG_RANDOM_SECRET_KEY" `
  --set-env-vars "DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require" `
  --set-env-vars "LIPILA_API_KEY=YOUR_LIPILA_API_KEY" `
  --set-env-vars "LIPILA_WEBHOOK_SECRET=YOUR_LIPILA_WEBHOOK_SECRET"
```

### Step 3 — Verify Backend Health Independently
Before connecting Firebase Hosting, verify the Cloud Run service responds healthy:
```powershell
curl https://<cloud-run-url>/health
```
Expected response:
```json
{"lipila_env":"sandbox","service":"edumanage-saas","simulator_enabled":false,"status":"healthy"}
```

### Step 4 — Deploy Firebase Hosting Rewrite & Static PWA Assets
```powershell
npx firebase-tools deploy --only hosting --project edumanage-7a46d
```
After deployment finishes, Firebase CLI will output your shareable links:
- **Primary Shareable App URL:** `https://edumanage-7a46d.web.app`
- **Alternative Firebase URL:** `https://edumanage-7a46d.firebaseapp.com`
- **School-Specific Shareable Link:** `https://edumanage-7a46d.web.app/s/<school-subdomain>`

---

## 4. Lipila Webhook & Environment Configuration

In your Lipila Merchant Dashboard ([dashboard.lipila.io](https://dashboard.lipila.io)):
- **Callback / Webhook URL:** `https://edumanage-7a46d.web.app/billing/webhook/lipila`
- **Environment Variables:**
  - `LIPILA_ENV`: `sandbox` (for `https://blz.lipila.io/api/v1`) or `production` (for `https://api.lipila.io/api/v1`)
  - `LIPILA_API_KEY`: Your merchant secret key (`x-api-key`)
  - `LIPILA_WEBHOOK_SECRET`: Secret used to verify webhook signatures (`X-Lipila-Signature` / `X-Webhook-Secret`)

> **Security Note:** The built-in Sandbox Simulator (`/billing/sandbox/<reference_id>`) is automatically disabled when `FLASK_ENV=production` or when `K_SERVICE` (Cloud Run) is set, ensuring simulated payments can never activate production subscriptions or clear real school fee balances.
