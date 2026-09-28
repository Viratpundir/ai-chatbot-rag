# NexaIQ web app

Next.js frontend for the Enterprise AI Knowledge Platform. It uses the FastAPI service in the parent project for authentication, document management, RAG chat, conversation history and admin health data.

## Run locally

Start the API from `enterprise-ai-platform`:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then start the web app from `enterprise-ai-platform/web`:

```powershell
npm install
npm run dev
```

Open http://localhost:3000. Browser requests use relative `/api/...` paths and Next.js proxies them to FastAPI at `http://127.0.0.1:8000` by default. To use another API address, set the server-only `API_BACKEND_URL` in `web/.env.local` (or use the existing `NEXT_PUBLIC_API_URL` as a fallback). Restart Next.js after changing this setting.

The protected Admin Dashboard is at `/admin`. It verifies the current user's role, requires administrator re-authentication, and fetches data from FastAPI admin routes that independently enforce roles.

## Create a development administrator

Set these backend-only values in `enterprise-ai-platform/.env` (never in frontend env files):

```dotenv
ADMIN_EMAIL=your-admin@example.com
ADMIN_PASSWORD=use-a-unique-strong-password
ADMIN_NAME=Platform Administrator
```

Then run from `enterprise-ai-platform`:

```powershell
..\.venv\Scripts\python.exe -m app.seed_admin
```

The command only runs with `APP_ENV=development`. It creates an ADMIN if that email is new, does nothing if it is already an active admin, and refuses to promote an existing employee by default. To explicitly promote an existing development account, set `ADMIN_PROMOTE_EXISTING=true`; that action changes the role and revokes that account's active sessions. No password is logged.

## Checks

```powershell
npm run lint
npm run build
```This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
