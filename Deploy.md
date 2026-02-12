# Deployment Guide

This guide covers deploying the Investment Analytics Platform to production using **Render** (backend), **Vercel** (frontend), and **Supabase** (database).

## Architecture Overview

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   Vercel        │       │    Render       │       │   Supabase      │
│   (Frontend)    │──────▶│   (Backend)     │──────▶│   (Database)    │
│   React+Vite    │       │   FastAPI      │       │   PostgreSQL    │
└─────────────────┘       └─────────────────┘       └─────────────────┘
     VITE_API_URL              CORS: FRONTEND_URL
```

---

## Prerequisites

- GitHub account connected to your repository
- [Supabase](https://supabase.com) account with a project created
- [Render](https://render.com) account
- [Vercel](https://vercel.com) account

---

## Step 1: Supabase Setup

### 1.1 Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) → New Project
2. Enter project details:
   - **Name**: `capstone-project-unfc` (or your preference)
   - **Database Password**: Generate and save securely
3. Wait for the project to provision (~2 minutes)

### 1.2 Get Credentials

1. Go to **Settings → API**
2. Copy these values:
   - **Project URL**: `https://xxxxx.supabase.co`
   - **anon public key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
   - **service_role key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`

### 1.3 Run Migrations

1. Go to **SQL Editor** in Supabase
2. Copy contents from `supabase/migrations/20260202192900_init_schema.sql`
3. Run the SQL to create tables
4. Repeat for any other migration files

### 1.4 Enable Row Level Security (RLS)

The migrations should include RLS policies. Verify in **Authentication → Policies** that:
- `assets` table: Public read access
- `historical_prices` table: Public read access

---

## Step 2: Deploy Backend to Render

### 2.1 Using Render Blueprint (Recommended)

1. Go to [render.com](https://render.com) → New → Blueprint
2. Connect your GitHub repository
3. Render should auto-detect `render.yaml`
4. Click **Apply** to deploy

### 2.2 Manual Setup (Alternative)

1. Go to [render.com](https://render.com) → New → Web Service
2. Connect your GitHub repository
3. Configure the service:

| Setting | Value |
|---------|-------|
| **Name** | `capstone-backend` |
| **Root Directory** | `.` (leave empty) |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | Free (or Starter for production) |

### 2.3 Configure Environment Variables

In the Render dashboard, go to **Environment** tab and add:

| Variable | Value | Note |
|----------|-------|------|
| `SUPABASE_URL` | `https://xxxxx.supabase.co` | From Supabase Settings → API |
| `SUPABASE_KEY` | `your-anon-key` | From Supabase Settings → API |
| `FRONTEND_URL` | `https://your-app.vercel.app` | Set after Vercel deployment |
| `PYTHON_VERSION` | `3.12.0` | Must include patch version |

### 2.4 Verify Backend is Running

After deployment, click the **URL** provided by Render. You should see:

```json
{"message":"Welcome to the Investment Analytics API"}
```

Test the health endpoint:
```
https://your-service.onrender.com/
```

---

## Step 3: Deploy Frontend to Vercel

### 3.1 Create Vercel Project

1. Go to [vercel.com](https://vercel.com) → Add New Project
2. Import your GitHub repository
3. Configure:

| Setting | Value |
|---------|-------|
| **Framework Preset** | Vite |
| **Root Directory** | `frontend` ← **Critical** |
| **Build Command** | `npm run build` (auto-detected) |
| **Output Directory** | `dist` (default) |

### 3.2 Configure Environment Variables

Add the following in Vercel → Settings → Environment Variables:

| Variable | Value | Environment |
|----------|-------|-------------|
| `VITE_API_URL` | `https://your-render-service.onrender.com` | Production |

> **Note**: `VITE_` prefix is required for Vite to expose the variable to the client.

### 3.3 Deploy

Click **Deploy**. Vercel will build and deploy your React frontend.

### 3.4 Verify Frontend

1. Click the **Visit** button after deployment
2. The app should load at `https://your-app.vercel.app`

---

## Step 4: Connect Backend and Frontend

### 4.1 Update Vercel with Render URL

If not already set, add `VITE_API_URL` in Vercel:
- **Variable**: `VITE_API_URL`
- **Value**: Your Render backend URL (e.g., `https://capstone-backend.onrender.com`)
- Redeploy if needed

### 4.2 Update Render with Vercel URL

In Render dashboard, add `FRONTEND_URL`:
- **Variable**: `FRONTEND_URL`
- **Value**: Your Vercel frontend URL (e.g., `https://capstone-frontend.vercel.app`)

Redeploy the backend to apply CORS changes.

### 4.3 Test End-to-End

1. Open your Vercel frontend URL
2. The app should fetch data from your Render backend
3. Check browser DevTools → Network tab for any failed requests

---

## Environment Variables Summary

### Render (Backend)

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon key |
| `FRONTEND_URL` | After Vercel deploy | Vercel frontend URL for CORS |
| `PYTHON_VERSION` | Yes | `3.12.0` |

### Vercel (Frontend)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | After Render deploy | Render backend URL |

---

## Troubleshooting

### Backend Issues

| Error | Solution |
|-------|----------|
| `SUPABASE_URL not set` | Add to Render Environment variables |
| `ModuleNotFoundError` | Check `requirements.txt` has all dependencies |
| CORS error | Verify `FRONTEND_URL` is set in Render |
| Build fails | Check Python version is `3.12.0` |

### Frontend Issues

| Error | Solution |
|-------|----------|
| API calls fail | Verify `VITE_API_URL` points to Render URL |
| Blank page | Check browser console for errors |
| Old API URL | Redeploy after setting `VITE_API_URL` |

### Supabase Issues

| Error | Solution |
|-------|----------|
| Table not found | Run SQL migrations in Supabase SQL Editor |
| Access denied | Check RLS policies in Supabase |

---

## Useful Commands

### Local Development

```bash
# Start backend
cd backend && uvicorn app.main:app --reload

# Start frontend
cd frontend && npm run dev
```

### Check Backend Health

```bash
curl https://your-render-service.onrender.com/
```

---

## Deployment Checklist

- [ ] Supabase project created and migrations run
- [ ] Render backend deployed with `SUPABASE_URL` and `SUPABASE_KEY`
- [ ] Vercel frontend deployed with `VITE_API_URL` set
- [ ] Render `FRONTEND_URL` updated with Vercel URL
- [ ] Backend redeployed after CORS changes
- [ ] End-to-end connection verified

---

## Architecture Files

The following files were created/modified for deployment:

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies for Render |
| `render.yaml` | Render Blueprint configuration |
| `backend/app/main.py` | CORS configuration for production |
| `frontend/src/api/client.ts` | Environment-based API URL |
| `frontend/.env.example` | Frontend env var documentation |
| `.env.example` | Backend env var documentation |
