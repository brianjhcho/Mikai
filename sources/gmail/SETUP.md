# Gmail Connector Setup

This guide walks you through connecting MIKAI to your Gmail account so it can read emails and extract intent signals from your INBOX and SENT folders.

No prior experience with Google Cloud is assumed. The whole process takes about 15 minutes.

---

## What you will need

- A Google account (the one whose Gmail you want to connect)
- Node.js installed (already required for MIKAI)
- The `googleapis` npm package (install with `npm install googleapis` from the MIKAI root)

---

## Step 1 — Create a Google Cloud project

1. Open [console.cloud.google.com](https://console.cloud.google.com) and sign in with your Google account.
2. Click the project selector at the top of the page (it may say "Select a project" or show an existing project name).
3. Click **New Project**.
4. Name it something like `MIKAI` and click **Create**.
5. Make sure the new project is selected in the top bar before continuing.

---

## Step 2 — Enable the Gmail API

1. In the left sidebar, go to **APIs & Services → Library**.
2. Search for **Gmail API**.
3. Click on it and then click **Enable**.

---

## Step 3 — Configure the OAuth consent screen

Before creating credentials, Google requires you to set up an OAuth consent screen. This is just a name and email — it is not published anywhere.

1. Go to **APIs & Services → OAuth consent screen**.
2. Select **External** as the user type and click **Create**.
3. Fill in:
   - **App name**: `MIKAI` (or anything you like)
   - **User support email**: your Google account email
   - **Developer contact email**: your Google account email
4. Click **Save and Continue** through the remaining screens (Scopes and Test Users can be left as defaults).
5. On the **Test Users** screen, click **Add Users** and add your own Google account email. Click **Save and Continue**.

---

## Step 4 — Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**.
2. Click **+ Create Credentials** at the top and choose **OAuth 2.0 Client ID**.
3. For **Application type**, select **Desktop app**.
4. Name it `MIKAI Desktop` (or anything you like) and click **Create**.
5. A dialog will show your **Client ID** and **Client Secret**. Click **Download JSON** to save them, or copy them manually.

You now have your `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`.

---

## Step 5 — Get a refresh token

A refresh token lets MIKAI access your Gmail without you having to log in each time. You generate it once using the script below.

### Create the token-exchange script

Create a temporary file called `get-gmail-token.mjs` anywhere on your machine (not inside the MIKAI repo):

```js
import { google } from 'googleapis';
import readline from 'readline';

const CLIENT_ID     = 'PASTE_YOUR_CLIENT_ID_HERE';
const CLIENT_SECRET = 'PASTE_YOUR_CLIENT_SECRET_HERE';
const REDIRECT_URI  = 'urn:ietf:wg:oauth:2.0:oob';

const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI);

const authUrl = oauth2Client.generateAuthUrl({
  access_type: 'offline',
  scope: ['https://www.googleapis.com/auth/gmail.readonly'],
  prompt: 'consent',
});

console.log('\nOpen this URL in your browser:\n');
console.log(authUrl);
console.log('');

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
rl.question('Paste the authorization code here: ', async (code) => {
  rl.close();
  const { tokens } = await oauth2Client.getToken(code);
  console.log('\nYour refresh token:\n');
  console.log(tokens.refresh_token);
  console.log('');
});
```

### Run the script

```bash
node get-gmail-token.mjs
```

1. The script will print a long URL. Open it in your browser.
2. Sign in with the Google account whose Gmail you want to connect.
3. Click **Allow** on the permissions screen (it will request read-only Gmail access).
4. Google will show you an authorization code. Copy it.
5. Paste the code back into the terminal prompt and press Enter.
6. The script will print your **refresh token**. Copy it.

You now have your `GMAIL_REFRESH_TOKEN`.

---

## Step 6 — Add credentials to .env.local

Open `.env.local` in the MIKAI root directory and add:

```
GMAIL_CLIENT_ID=your_client_id_here
GMAIL_CLIENT_SECRET=your_client_secret_here
GMAIL_REFRESH_TOKEN=your_refresh_token_here
```

Replace the placeholder values with what you copied in the steps above.

---

## Step 7 — Add the sync script to package.json

Open `package.json` and add this line inside the `"scripts"` section:

```json
"sync:gmail": "tsx sources/gmail/sync.js"
```

---

## Step 8 — Test it

Run a dry-run first to confirm everything is connected without writing any data:

```bash
npm run sync:gmail -- --dry-run
```

You should see a list of emails that would be ingested. If you see an error about credentials, re-check the values in `.env.local`.

To do a real sync:

```bash
npm run sync:gmail
```

Then run the graph extraction step as usual:

```bash
npm run build-graph
```

---

## Available flags

| Flag | What it does |
|------|-------------|
| `--dry-run` | Print what would be ingested without writing anything |
| `--days N` | How far back to look (default: 90 days) |
| `--label INBOX` | Only scan your inbox |
| `--label SENT` | Only scan your sent mail |
| `--force` | Re-ingest everything, ignoring previous sync state |
| `--host URL` | Point at a different API host (default: http://localhost:3000) |

---

## Troubleshooting

**"OAuth2 token refresh failed"**
Your refresh token has expired or was revoked. Re-run the `get-gmail-token.mjs` script from Step 5 to generate a new one and update `.env.local`.

**"Missing Gmail credentials in .env.local"**
One or more of `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, or `GMAIL_REFRESH_TOKEN` is missing from `.env.local`. Check all three are present.

**"0 pending" even though you have emails**
The sync only ingests emails that contain action verbs (book, buy, schedule, call, etc.) in the subject line or first few lines of the body. This is intentional — MIKAI targets intent-bearing emails, not newsletters or receipts.

**Google shows "This app is not verified"**
Click **Advanced → Go to MIKAI (unsafe)** on the consent screen. This warning appears for apps still in testing mode. Since you added yourself as a test user in Step 3, this is expected and safe.
