# Contributing

## Development Workflow

1. Fork repository and create a feature branch.
2. Keep PRs focused and small.
3. Add/adjust tests for behavior changes.
4. Update docs when API or config changes.

## Security Requirements

- Never commit real secrets, tokens, or credentials.
- Use `.env.example` placeholders only.
- Report vulnerabilities privately to maintainers.

## Code Standards

- Follow existing Python style and type hints.
- Keep functions small and readable.
- Avoid debug prints in committed code.

## Pull Request Checklist

- [ ] No secrets in diff
- [ ] Lint/tests pass locally
- [ ] Docs updated if needed
- [ ] Backward compatibility considered
