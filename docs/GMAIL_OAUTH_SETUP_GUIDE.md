# WorkFlowOS — Gmail OAuth 2.0 Setup Guide (Read-Only)

**Phase:** 8.4 — Local OAuth Token Helper  
**Scope:** `https://www.googleapis.com/auth/gmail.readonly`  
**Application Type:** Google Cloud Desktop OAuth Client (RFC 8252)

---

## 1. Security & Safety Rules

To protect your personal and cloud credentials, WorkFlowOS enforces the following security boundaries:

- **Strict Read-Only Access:** Requests **ONLY** `https://www.googleapis.com/auth/gmail.readonly`. Under no circumstances are `gmail.modify`, `mail.google.com`, or full-access scopes used.
- **Zero Console Exposure:** The helper script **never prints** Client Secrets or Refresh Tokens to stdout, stderr, or log files.
- **Zero Automatic File Mutation:** The script **does not modify** the active `.env` file automatically.
- **Git Isolation:** Both `credentials.json` and generated token files (`.gmail_token.local`) are strictly listed in `.gitignore` and must never be staged or committed.
- **Local Isolation:** Credentials are never transmitted to any third-party server. Authorization redirects exclusively to a local ephemeral loopback server (`http://localhost:<ephemeral-port>`).

---

## 2. Where to Download the Desktop OAuth Client JSON

The developer has already created the Google Cloud Project, enabled the Gmail API, and configured the OAuth consent screen with the test user and `gmail.readonly` scope.

To download the Desktop Client configuration:

1. Open the [Google Cloud Console Credentials Page](https://console.cloud.google.com/apis/credentials).
2. Ensure your WorkFlowOS project is selected in the top project dropdown.
3. In the **OAuth 2.0 Client IDs** table, locate your client:
   - Verify that **Type** is **Desktop app** (or Installed Application).
4. Click the **Download JSON** button (downward arrow icon) on the far right of the row.
5. The downloaded file will typically be named something like `client_secret_<client-id>.json`.

---

## 3. Where to Place the Downloaded JSON

You can place the file directly in the WorkFlowOS project root:

```
c:\Users\navad\.cache\Desktop\Hackthon\credentials.json
```

Rename the downloaded file to `credentials.json`, or keep its original name (the script automatically recognizes any `client_secret*.json` in the root).

Alternatively, you can keep the file anywhere on your system and pass its path using the `--credentials` flag.

### Verify Git Protection:
Before proceeding, confirm that git ignores the credentials file:
```bash
git check-ignore -v credentials.json
```
*Expected output: `.gitignore:14:credentials.json credentials.json`*

---

## 4. How to Run the Setup Script

Run the helper script from PowerShell or your preferred terminal in the project root:

```powershell
python scripts/gmail_oauth_setup.py
```

### Optional Command-Line Arguments:
- `--credentials <path>` or `-c <path>`: Specify a custom path to your downloaded client secrets JSON.
- `--output <path>` or `-o <path>`: Specify an alternative output file for the generated tokens (default: `.gmail_token.local`).
- `--show-url`: Display the authorization URL in the terminal (useful if your default browser does not launch automatically).

Example with custom path:
```powershell
python scripts/gmail_oauth_setup.py --credentials "C:\Users\navad\Downloads\client_secret.json"
```

---

## 5. Where Browser Authorization Happens

When you run the script:

1. **Local Server Start:** The script starts a temporary, local loopback web server on an ephemeral port (e.g., `http://localhost:54321/`).
2. **Browser Launch:** Your default system web browser automatically launches and navigates to Google's OAuth 2.0 consent page.
3. **Account Sign-In:** 
   - Sign in using the **configured Gmail test user** account.
   - If prompted with *"Google hasn't verified this app"*, click **Advanced** -> **Go to WorkFlowOS (unsafe)** (this warning appears because your Google Cloud project is in internal/external testing mode).
4. **Scope Verification:**
   - Verify that the consent screen requests only:
     > **View your email messages and settings** (`gmail.readonly`)
   - Click **Continue** / **Allow**.
5. **Completion in Browser:**
   - The browser will display:  
     `WorkFlowOS authorization complete! You may close this tab and return to your terminal.`
   - You can now safely close the browser tab.

---

## 6. How to Securely Obtain and Store the Refresh Token

Once authorization completes, the script prints strictly:

```
Gmail OAuth authorization completed successfully.
Refresh token generated. Store it securely in your local .env.
```

The script writes your credentials safely to the gitignored file:
```
c:\Users\navad\.cache\Desktop\Hackthon\.gmail_token.local
```

### Steps to store in `.env`:

1. Open `.gmail_token.local` in your editor. It contains:
   ```ini
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REFRESH_TOKEN=1//04_your_refresh_token_here
   ```
2. Copy these three values into your local `.env` file located at the project root:
   ```ini
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REFRESH_TOKEN=1//04_your_refresh_token_here
   ```
3. Save `.env`.
4. **Delete `.gmail_token.local`** to avoid leaving credentials on disk:
   ```powershell
   Remove-Item .gmail_token.local
   ```

---

## 7. Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **`credentials.json not found`** | File missing from project root | Download the Desktop OAuth Client JSON from Google Cloud Console and place it as `credentials.json` or pass `--credentials <path>`. |
| **`Access blocked: WorkFlowOS has not completed Google verification`** | Account is not added as a test user | In Google Cloud Console, navigate to **APIs & Services** -> **OAuth consent screen** -> **Test users**, and add your Gmail address. |
| **`Error: Google did not return an OAuth refresh token`** | User was already consented without offline prompt | Visit [Google Account Permissions](https://myaccount.google.com/permissions), revoke access for WorkFlowOS, and re-run the script. |
| **Browser does not open automatically** | Environment has restricted GUI browser launching | Run `python scripts/gmail_oauth_setup.py --show-url` and manually copy/paste the authorization URL into your browser. |
