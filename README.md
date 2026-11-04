# SchoolStacks 🎓

> **A Modern, Multi-Tenant School Management & SaaS Platform** designed for schools, academies, and educational institutions across Africa and worldwide. Built with Python (Flask), React (TypeScript & Vite), PostgreSQL / SQLite, and integrated with Lipila mobile money payments.

---

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=flat&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-5.4-646CFF?style=flat&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=flat&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PWA](https://img.shields.io/badge/PWA-Ready-orange?style=flat&logo=pwa&logoColor=white)](#progressive-web-app-pwa)

---

## 🌟 Overview

**SchoolStacks** is a full-featured, multi-tenant school operations platform that streamlines daily administrative, academic, financial, and communication workflows into a single unified system.

Whether self-hosted by an individual institution or run as a multi-school SaaS platform, SchoolStacks provides dedicated portals, automated role-based access control, billing workflows with mobile money (Airtel, MTN, Zamtel via Lipila), automated PDF report card generation, and offline-capable Progressive Web App (PWA) support.

---

## ✨ Features by Role

### 🏫 Platform Superadmin
- **Multi-Tenant Management**: Provision, onboard, monitor, suspend, and manage individual schools.
- **SaaS Subscription Plans**: Configure tier pricing (Starter, Professional, Enterprise) and billing frequencies.
- **Platform Analytics**: High-level metrics on total schools, active students, platform revenue, and system health.
- **Audit Logging**: Comprehensive security audit trail of sensitive actions and system logins.

### 🏛️ School Administrator
- **Student & Teacher Registration**: Manage full student profiles, admission numbers, guardian contacts, and teacher assignments.
- **Academic Setup**: Configure terms, academic years, classes, subject offerings, and school timetables.
- **Fee Management**: Set fee structures per class/term, record payments, generate printable digital receipts, and track arrears.
- **School Announcements**: Broadcast targeted notifications to teachers, students, or parents.

### 👩‍🏫 Teacher Portal
- **Attendance Tracking**: Mark and monitor daily student attendance with automated parent notifications.
- **Assignment Management**: Post homework, set deadlines, attach resources, and collect digital submissions.
- **Grading & Results**: Grade submissions with feedback and enter exam marks per term/subject.
- **Study Materials**: Upload learning resources, syllabus documents, and lecture notes.

### 🎒 Student Portal
- **Dashboard Overview**: Check pending homework, upcoming timetable slots, and latest announcements.
- **Assignment Submissions**: Upload homework submissions directly through the portal.
- **Academic Progress**: Review exam marks, term rankings, and download official PDF report cards.
- **Fee Status**: View fee balances, payment histories, and invoices.

### 👨‍👩‍👧 Parent Portal
- **Multi-Child Dashboard**: Link and monitor multiple children under a single guardian account.
- **Attendance Insights**: Instant visibility into attendance status and absences.
- **Fee Payments**: View fee breakdown and pay fees securely via mobile money.
- **Direct Academic Reports**: Download report cards and track academic growth term-by-term.

### 💳 Mobile Money & Billing (Lipila Integration)
- **Local Payment Gateways**: Built-in support for Airtel Money, MTN Mobile Money, and Zamtel Kwacha via Lipila.
- **Automated Webhooks**: Immediate payment confirmation and automated receipt generation upon completed transactions.
- **Sandbox Simulator**: Built-in test sandbox environment for seamless development and verification.

### 📱 Progressive Web App (PWA)
- **Installable**: Installable as a native-like app on Android, iOS, Windows, and macOS.
- **Offline Fallback**: Offline detection with cached static assets and helpful offline status screens.

---

## 🏗️ Architecture & Tech Stack

```mermaid
graph TD
    Client["Clients (Browser / Mobile PWA)"] --> Web["Firebase Hosting / Reverse Proxy"]
    Web --> App["Flask Application (WSGI / Gunicorn)"]
    App --> Tenant["Multi-Tenant Resolver (Subdomain & /s/<school>)"]
    App --> DB[("PostgreSQL / SQLite")]
    App --> Lipila["Lipila Mobile Money API"]
    App --> Storage["Uploads & Storage Engine"]
    App --> PDF["ReportLab PDF Generator"]
```

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.12+, Flask 3.0, Flask-SQLAlchemy, Flask-Login, Flask-Migrate (Alembic), Gunicorn |
| **Frontend** | React 18, TypeScript, Vite, Bootstrap 5.3, Bootstrap Icons, HTML5 / Jinja2 |
| **Database** | PostgreSQL (Production) / SQLite (Development & Testing) |
| **Payments** | Lipila API (Mobile Money: Airtel, MTN, Zamtel) |
| **Documents** | ReportLab (Dynamic PDF report cards and receipts) |
| **Deployment** | Docker, Google Cloud Run, Firebase Hosting |

---

## 📂 Project Structure

```text
schoolstacks/
├── app.py                     # Flask application factory and route mappings
├── config.py                  # Environment configurations (Dev, Testing, Prod)
├── wsgi.py                    # WSGI entrypoint for Gunicorn/production
├── models.py                  # SQLAlchemy multi-tenant database models
├── extensions.py              # Initialized extensions (db, login_manager, migrate)
├── helpers.py                 # Core helper functions and filters
├── tenant.py                  # Multi-tenant resolver and context handlers
├── utils.py                   # Email, PDF report card, and notification helpers
├── migrations_helper.py       # Safe automated database schema migration utilities
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Production container image definition
├── firebase.json              # Firebase Hosting configuration & Cloud Run rewrites
│
├── blueprints/                # Modular application controllers
│   ├── auth.py                # Authentication and password recovery
│   ├── superadmin.py          # Platform owner & SaaS management
│   ├── admin.py               # School administration & operations
│   ├── teacher.py             # Teacher workflows & grading
│   ├── student.py             # Student portal & assignments
│   ├── parent.py              # Guardian portal & fee tracking
│   ├── billing.py             # Subscriptions & Lipila payment processing
│   ├── onboarding.py          # School tenant self-registration
│   └── api.py                 # RESTful endpoints for SPA/PWA
│
├── services/                  # External service integrations
│   └── lipila.py              # Lipila payment gateway client & webhook handler
│
├── frontend/                  # React + TypeScript + Vite frontend
│   ├── src/                   # React components, pages, and hooks
│   ├── public/                # Static assets & icons
│   ├── package.json           # Frontend package manifest
│   └── vite.config.ts         # Vite build configuration
│
├── static/                    # Backend static files, PWA manifest, service worker
├── templates/                 # Jinja2 templates (dashboards, receipts, landing)
├── migrations/                # Alembic database migrations
└── tests/                     # Automated test suites (pytest)
    ├── test_edumanage.py      # Core end-to-end integration tests
    └── test_audit_e2e.py      # Multi-tenant audit trail tests
```

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.12+**
- **Node.js 18+** & **npm**
- **Git**
- Optional: **PostgreSQL 14+** (SQLite is used by default in development)

---

### 1. Clone the Repository

```bash
git clone https://github.com/Sivhila/schoolstacks.git
cd schoolstacks
```

---

### 2. Backend Setup

1. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy the example environment file and customize it:
   ```bash
   cp .env.example .env
   ```

4. **Initialize the Database:**
   ```bash
   flask db upgrade
   ```
   *(Or run the application directly; automated schema helper will initialize tables automatically on first run).*

5. **Start the Flask Development Server:**
   ```bash
   python app.py
   ```
   The backend will be available at: `http://localhost:5000`

---

### 3. Frontend Setup (React SPA)

If you wish to modify or build the React frontend:

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node dependencies:**
   ```bash
   npm install
   ```

3. **Start the Vite development server:**
   ```bash
   npm run dev
   ```

4. **Build for Production:**
   ```bash
   npm run build
   ```
   Compiled assets are generated in `frontend/dist/` and automatically served by Flask in production.

---

## ⚙️ Environment Configuration

Key environment variables in `.env`:

| Variable | Description | Default |
|---|---|---|
| `FLASK_ENV` | Environment mode (`development`, `production`, `testing`) | `development` |
| `SECRET_KEY` | Cryptographic key for session signing | `dev-secret-key` |
| `DATABASE_URL` | PostgreSQL connection string | `sqlite:///instance/edumanage.db` |
| `BASE_DOMAIN` | Root domain for multi-tenant subdomains | `localhost:5000` |
| `SUPERADMIN_EMAIL`| Default platform superadmin email | `superadmin@schoolstacks.zm` |
| `SUPERADMIN_PASSWORD` | Default platform superadmin initial password | `SuperAdmin@2026` |
| `LIPILA_ENV` | Lipila payment environment (`sandbox` or `production`) | `sandbox` |
| `LIPILA_API_KEY` | Lipila API authentication key | *None* |
| `LIPILA_CURRENCY` | Currency code for billing and fees | `ZMW` |
| `MAIL_SERVER` | SMTP email server hostname | *None* |
| `MAIL_USERNAME` | SMTP email username | *None* |
| `MAIL_PASSWORD` | SMTP email password | *None* |

---

## 🧪 Running Tests

The test suite covers multi-tenancy isolation, role authorization, fee payments, Lipila webhook verification, and audit logging:

```bash
# Run all automated tests
pytest

# Run tests with verbose output
pytest -v

# Run specific test suite
pytest tests/test_edumanage.py
```

---

## 🐳 Docker & Cloud Deployment

### Docker Container

Build and run using Docker:

```bash
# Build the container image
docker build -t schoolstacks .

# Run the container
docker run -p 8080:8080 \
  -e FLASK_ENV=production \
  -e SECRET_KEY="your-production-secret" \
  -e DATABASE_URL="postgresql://user:pass@host:5432/schoolstacks" \
  schoolstacks
```

### Google Cloud Run & Firebase Hosting

SchoolStacks is pre-configured for seamless deployment to **Google Cloud Run** with **Firebase Hosting** as a reverse proxy:

1. **Deploy backend to Cloud Run:**
   ```bash
   gcloud run deploy schoolstacks-backend \
     --source . \
     --region us-central1 \
     --allow-unauthenticated
   ```

2. **Deploy frontend & static routing to Firebase:**
   ```bash
   firebase deploy --only hosting
   ```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
