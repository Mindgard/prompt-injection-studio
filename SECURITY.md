# Security Policy

## Intended use

Prompt Injection Studio generates and delivers prompt injection payloads. It
is built for authorised security testing: systems you own, or systems you
have written permission to test. Using it against anything else is likely
illegal in your jurisdiction.

Some capabilities carry real-world reach and deserve care:

- `pistudio serve --host 0.0.0.0` exposes a payload server to your whole
  network. The default binding is `127.0.0.1`; keep it that way on networks
  you do not control.
- The `ngrok` extra publishes payloads to a public URL.
- Hardware delivery (BadUSB, BLE, evil portal, DNS interception, network
  MITM) affects devices and users nearby, not just your target.
- The `edge-tts` engine sends payload text to a Microsoft endpoint. Nothing
  else in the tool leaves your machine.

## Reporting a vulnerability

Email **security@mindgard.ai** rather than opening a public issue. Include
reproduction steps and affected version. We aim to acknowledge within three
working days.

Please do not report the tool's intended offensive capabilities as
vulnerabilities. Bugs in the tool itself — command injection through a
payload name, a path traversal in deployment, credentials written to disk —
are very much in scope.
