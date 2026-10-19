# Setting up the Anthropic key for "Ask about the data"

## 1. Create a workspace (so the site has its own spending cap)
1. Go to **console.anthropic.com**.
2. Left sidebar → **Settings** → **Workspaces**.
3. Click **Create workspace**.
   - Name: `half-life-site`
   - Leave everything else at the default → **Create**.

> Don't see "Workspaces"? Skip to step 3 and pick **Default workspace** as the scope, then set the cap under **Settings → Limits** instead (it applies to your whole account).

## 2. Set the monthly spending cap
1. Click into the **half-life-site** workspace.
2. Open its **Limits** tab/section.
3. Set **Monthly spend limit** to **$10**. Leave any rate limits at their defaults.

## 3. Create the API key
1. Left sidebar → **API Keys** → **Create key**.
2. Name: `food-churn-nyc-web`
3. Expires: **Never**
4. Scope: **half-life-site** (the workspace you just made)
5. **Create key**, then copy it. It's shown only once.

**Don't paste the key into the Claude chat.**

## 4. Put the key in the project (local)
1. Open `web/.env.local`. In a terminal: `open -e "/Users/junaid/Developer/Claude Vibecoding/nyc-food-churn/web/.env.local"`
2. Find the line `ANTHROPIC_API_KEY=` and paste the key right after the `=` (no quotes, no spaces).
3. Save and close.

## 5. Put the key in Vercel (live site)
1. vercel.com → project **half-life-nyc** → **Settings** → **Environment Variables**.
2. Add **Key** `ANTHROPIC_API_KEY`, **Value** = the key, for **all environments** → **Save**.
3. **Deployments** → latest deployment → **⋯** → **Redeploy**.

Then tell Claude "key is in" to test it.
