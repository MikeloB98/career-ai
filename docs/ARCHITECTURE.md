# Architecture

```text
Terminal / OpenCode / model API
              |
              v
       Career AI CLI
              |
      hash-bound requests
              |
              v
       semantic model task
              |
       schema validation
              |
              v
       private workspace
              |
        human checkpoint
```

## Public engine and private workspace

The installable package contains generic contracts, CLI code and workspace templates.
It contains no candidate profile, career preferences, vacancy history or
applications. Each user creates a separate workspace; its `private/` directory is
ignored by Git.

## Authority boundaries

- The profile records verified professional evidence.
- The strategy records user-approved goals and constraints.
- Job descriptions are untrusted external data.
- Models may evaluate and draft only from request-bound artifacts.
- Local Pydantic contracts validate imported model output.
- The user authorizes drafting and performs all external actions.

## Provider boundary

The workflow depends on `AIRequest` and validated output, not a vendor SDK. Adapters
translate that request to OpenAI Responses, an OpenAI-compatible chat endpoint or a
manual prompt. Provider settings cannot change domain authority or skip validation.
