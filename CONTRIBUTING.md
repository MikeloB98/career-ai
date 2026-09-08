# Contributing

Use Python 3.11 or newer and keep all examples synthetic.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

Do not commit real CVs, vacancies, application materials, API keys, browser sessions or
provider responses containing personal data. New model adapters must preserve the
existing request bindings, output validation and human-action boundaries.
