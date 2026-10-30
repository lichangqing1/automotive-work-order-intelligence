# Recruiter landing page

This site is the 60-second, evidence-first introduction to the Automotive Work Order AI Quality Engineering Platform. It is intentionally separate from the Streamlit engineering console.

**Live site:** https://automotive-ai-quality-engineering.dearmole20.chatgpt.site

Metrics are generated from the sanitized reports under `artifacts/ai_value/`:

```bash
python scripts/export_landing_data.py
cd landing
pnpm dev
```

Before publishing, regenerate the data and run `pnpm build`. The page presents the current `BLOCK` decisions and limitations rather than implying autonomous production approval.

To expose the recruiter-facing source buttons, configure the real public repository URL before building:

```bash
export NEXT_PUBLIC_GITHUB_URL="https://github.com/lichangqing1/automotive-work-order-intelligence"
pnpm build
```

The public repository URL is also the checked-in fallback, so packaged and local builds retain a working source link. The environment variable remains available for forks.
