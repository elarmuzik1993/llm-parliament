# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | ✅ Current |
| 0.1.x   | ❌ No longer receiving fixes |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report privately via [GitHub Security Advisories](https://github.com/elarmuzik1993/llm-parliament/security/advisories/new)
or by emailing **elar.muzik@gmail.com** with the subject line `[llm-parliament] Security`.

Include:
- Description of the vulnerability and its potential impact
- Steps to reproduce
- Any suggested fix if you have one

You can expect an acknowledgement within 72 hours and a fix or mitigation
plan within 14 days for confirmed issues.

## Scope

LLM Parliament is a local CLI tool — it makes no inbound network connections
and runs no server. The relevant security surface is:

**In scope:**
- API key exposure (storage in keyring or `keys.env`, logging, error messages)
- Unsafe file permissions on config or key files
- Command injection via user-supplied input (question text, config values)
- Dependency vulnerabilities with a realistic exploit path

**Out of scope:**
- Vulnerabilities in LLM provider APIs (Anthropic, Google, OpenAI, Ollama)
- Model outputs, jailbreaks, or prompt injection against the LLMs themselves
- Issues that require physical access to the machine or an already-compromised account
- Social engineering

## Security design notes

- API keys are stored in the OS native credential store (Windows Credential
  Manager, macOS Keychain, GNOME Keyring) via the `keyring` library. A plain
  `~/.parliament/keys.env` file (`chmod 0600` on Unix) is used as a fallback.
- No keys or sensitive config values are logged or included in Hansard output.
- The tool makes outbound HTTPS calls only to the providers explicitly
  configured by the user.
- `/update` and `parliament update` run `git pull`, `pipx upgrade`, or
  `pip install` — only for the `llm-parliament` package itself.
