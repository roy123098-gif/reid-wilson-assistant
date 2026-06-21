# Reid & Wilson Wix Setup

The local app is ready for testing. Publishing it requires a public backend address because Wix cannot run the Python calculation engine.

## 1. Test Locally

Open the local address shown when the server starts.

Turn on **Test Mode** and try all three EIC sample profiles. Use **Estimate Tax & Refund** and confirm every limitation is visible. Open **ITIN Guide** and complete both a new-application path and the "eligible for an SSN" path. Test Mode does not save the samples.

## 2. Upload the Deployment Folder

Create a private GitHub repository and upload the contents of the `reid_wilson_web` folder. Do not upload `.tax_data`, `analytics.json`, or any real taxpayer information.

## 3. Create the Render Service

1. Sign in to Render.
2. Choose **New** and then **Blueprint**.
3. Connect the private GitHub repository.
4. Select the included `render.yaml` file.
5. Deploy the service.
6. Open the Render address and confirm `/api/health` shows `"ok": true`.

The included configuration automatically turns on public-safe mode. In this mode, profiles are not written to the server and question text is not saved in analytics.

The Render configuration also requires HTTPS, disables profile persistence, disables question analytics, and installs authenticated encryption support. Do not add `PROFILE_ENCRYPTION_KEY` to GitHub. If encrypted server-side storage is introduced later, create the key in the hosting provider's secret manager and arrange durable encrypted storage first.

## 4. Add It to Wix

1. Open the Wix editor for ReidandWilson.com.
2. Add a page named **EIC Assistant** and set its page address to `/eic`.
3. Choose **Add Elements**, **Embed Code**, then **Embed a Site**.
4. Paste the public Render address.
5. Make the embedded area full width and about 1,100 pixels tall.
6. Check the desktop and mobile Wix layouts.
7. Publish the Wix site.

For Android installation, a normal Wix button linking to a dedicated address such as `https://app.reidandwilson.com` is better than an iframe. The install prompt belongs to the app's own address and may not work inside an embedded Wix frame. See `ANDROID_SETUP.md` for the Play Store path.

The `wix_embed_snippet.html` file is available if the Wix editor asks for HTML instead of a website address. Replace `YOUR-RENDER-ADDRESS` first.

## 5. Optional Settings

In the Render service settings, add:

- `DONATION_URL`: the complete HTTPS address for a donation page. The support link stays hidden until this is set.
- `ALLOWED_ORIGINS`: keep `https://reidandwilson.com,https://www.reidandwilson.com`.

## Before Public Promotion

- Have the privacy notice and terms reviewed professionally.
- Use only fictional information during testing.
- Do not collect Social Security numbers, tax documents, addresses, or bank information.
- Confirm every 2025 EIC example against the IRS EITC Assistant.
- Confirm every tax and refund scenario against completed 2025 Form 1040 software before describing the result as reliable.
- Confirm ITIN instructions, processing times, links, and document language against the current IRS Form W-7 instructions.
- Do not advertise ITIN preparation, document authentication, or filing until the service model has professional legal and compliance review.
- Add user accounts only after a secure database and account-deletion process are ready.
