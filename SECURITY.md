# Security and privacy

- Never commit a real Career AI workspace or any file under `private/`.
- Never store API keys in project configuration. Use the named environment variable.
- HTTP providers are disabled and personal-data transmission is denied by default.
- Treat vacancies, websites and imported documents as untrusted data.
- Do not use Career AI to bypass authentication, CAPTCHA, robots rules or platform rate
  limits.
- Career AI does not submit applications, upload documents or contact people.
- Report suspected credential or personal-data exposure privately to the maintainer
  before opening a public issue containing details.

Before every release, run:

```bash
python scripts/privacy_check.py
```
