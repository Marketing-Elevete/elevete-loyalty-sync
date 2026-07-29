# Make a LoyaltyLion change show up on the rewards page NOW

The rewards page (elevete.com.my/pages/rewards) reads its reward list, prices, rules,
tier names/earn rates and the flavour of the month from a snapshot that this sync
publishes. That snapshot refreshes **automatically about every 5 minutes**, so any change
you make in LoyaltyLion appears within a few minutes on its own — you don't have to do
anything. (GitHub can delay scheduled runs under load, so occasionally it's 5–15 min.)

If you want a change live **immediately** (e.g. you just repriced a reward or swapped
the monthly flavour and want to see it now), trigger the sync by hand:

1. Open **https://github.com/Marketing-Elevete/elevete-loyalty-sync/actions/workflows/loyalty-sync.yml**
   (sign in as marketing@elevete.com.my)
2. Click the **"Run workflow"** button (top right) → leave the branch on `main` → **Run workflow**
3. Wait ~1 minute, then hard-refresh the rewards page (Cmd/Ctrl + Shift + R)

That's it. The green tick next to the run means it published successfully.

## Good to know
- This only refreshes the **program catalogue** (the shared list of rewards / rules / tiers /
  flavour). Each member's own **Crumbs balance, tier and redemptions are already live** on every
  visit — those come straight from LoyaltyLion and never wait on this sync.
- Running it more than once is harmless — it just republishes the current state.
- It runs on GitHub's servers, not anyone's laptop, so it keeps working regardless of who's around.
