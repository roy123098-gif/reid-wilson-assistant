# Reid & Wilson Money Coach Web + Plaid Backend

This folder is the responsive website version of the Android Money Coach and the secure server contract used by both clients.

## Included user features

- Home summary, Spending, Budget, Goals, Coach, and Trust Center
- Fast manual transaction add/edit/delete
- CSV import/export with quoted-field support
- Full JSON backup and restore
- IndexedDB local-first storage that survives normal website updates
- Responsive keyboard, touch, and screen-reader-friendly layouts
- Optional Plaid Sandbox linking with clear test-data labels
- Privacy, terms, support, and data-deletion pages

## Security model

- The Plaid client ID and secret exist only in hosting environment variables.
- Browsers and Android receive an opaque random session token, never a Plaid access token.
- Plaid access tokens are encrypted with AES-256-GCM before database storage.
- Client-provided user IDs are not trusted; the server derives an internal user from the bearer session.
- Production refuses to start without `DATABASE_URL` and `TOKEN_ENCRYPTION_KEY`.
- CORS, CSP, HTTPS/HSTS, rate limits, payload limits, and safe event logging are enabled.
- Disconnect revokes the Plaid Item before deleting the local server record.

## Routes

- `GET /health` and `GET /api/health`
- `POST /api/session/register`
- `DELETE /api/session/data`
- `POST /api/plaid/link-token`
- `POST /api/plaid/exchange`
- `POST /api/plaid/sync`
- `POST /api/plaid/disconnect`
- `POST /api/plaid/webhook`

Plaid client routes require `Authorization: Bearer <opaque-session-token>`. The webhook route intentionally does not require a user session.

## Local verification

1. Copy `.env.example` to `.env` and keep it out of source control.
2. Leave Plaid values blank to verify the safe manual-mode fallback.
3. Run `npm install`, `npm run build`, and `npm start`.
4. Open `http://localhost:8787` and test all screens.

Local development uses a private JSON store only when `NODE_ENV` is not `production`. Production requires Postgres.

## Hosting values

Set these privately in Render; never add the values to GitHub:

- `NODE_ENV=production`
- `DATABASE_URL` from the attached Render Postgres instance
- `TOKEN_ENCRYPTION_KEY` as a long random generated secret
- `PLAID_ENV=sandbox`
- `PLAID_CLIENT_ID`
- `PLAID_SECRET`
- `PLAID_PRODUCTS=transactions`
- `PLAID_COUNTRY_CODES=US`
- `APP_PACKAGE_NAME=reid.wilson.moneycoach`
- `PLAID_WEBHOOK_URL=https://api.reidandwilson.com/api/plaid/webhook`
- `PLAID_REDIRECT_URI=https://api.reidandwilson.com/`
- `ALLOWED_ORIGINS=https://reidandwilson.com,https://www.reidandwilson.com,https://app.reidandwilson.com,https://api.reidandwilson.com`

Use a separate Node web service with this folder as its root. The existing legacy Python tax assistant remains recoverable in repository history and can stay online until the Money Coach service is verified and the Wix embed is changed.
