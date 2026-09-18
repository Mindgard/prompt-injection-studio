# Flipper bridge protocol

The serial protocol between `pistudio.hardware.flipper.bridge.FlipperBridge`
and the companion FAP running on the Flipper Zero.

> **Verified against the firmware.** Checked line by line against
> `src/serial/bridge_protocol.c` in
> [flipperzero-prompt-injection-field-kit](https://github.com/Mindgard/flipperzero-prompt-injection-field-kit)
> (app `mindgard_pifk`, `fap_version=(1, 1)`). Where the two disagree the
> firmware is correct and this file is the bug.

> **Conversation support was removed** from both sides. The host no longer
> sends `LIST CONVOS`, `EXEC CONVO` or `SET CONVO_DELAY` and no longer writes
> `conversations.json`; the current firmware implements none of those verbs
> and its `STATUS` reply no longer carries a `convos=` field. The host still
> ignores unrecognised `key=value` fields, so older firmware keeps working.

## Transport

| Property | Value |
|---|---|
| Baud rate | 115200 |
| Framing | One command per line, terminated `\r\n` |
| Encoding | UTF-8 |
| Response terminator | `\r\n` |
| Max command line | 256 bytes (`MINDGARD_SERIAL_BUF_SIZE`); longer is refused with `ERR command too long` |
| Host read buffer | 65536 bytes — a host-side cap, not a protocol limit |
| Default read timeout | 2 seconds |

Remote Mode switches the Flipper's USB to dual-CDC. Channel 0 remains the
Flipper's own CLI; channel 1 carries this protocol. When two Flipper serial
ports are present the host takes the higher-numbered one. Sending `LIST` to
channel 0 gets ``could not find command `LIST` `` from the Flipper's own
shell — a useful way to confirm the app is not in Remote Mode.

Commands must not contain a newline — the host rejects any that do, because
the second line would arrive as a separate command. Command matching is
**case-insensitive**, and longer prefixes are tested before shorter ones so
`STOP BLEGATT` is not swallowed by `STOP BLE`.

## Response grammar

Every response is a single line beginning with a status token:

| Prefix | Meaning |
|---|---|
| `OK` | Success; further words are command-specific |
| `ERR` | Failure; the remainder is a human-readable reason |
| `DATA ` | A JSON array follows on the same line |

Execution commands are **synchronous**: the reply arrives once the action has
finished, so there is no separate "started" message.

## Commands

The firmware implements twenty-four verbs. The host currently drives the
subset marked ✅; the rest are reachable over a raw serial connection but have
no `hw flipper` command yet.

### Session

#### `PING` ✅

Heartbeat. Used to confirm the FAP is in Remote Mode before anything else.

- **Returns:** `OK PONG`

#### `STATUS` ✅

- **Returns:** `OK STATUS <state> payloads=<n>`
- `<state>` is one of `idle`, `listening`, `connected`, `executing`, `error`.
- Counts that are not integers are treated as 0 and logged; a malformed
  status must not abort the query.
- Unrecognised `key=value` fields are ignored rather than rejected, so
  firmware reporting extra counts still parses.

#### `LIST` ✅

- **Returns:** `DATA [{...}, ...]` — a JSON array on one line.
- Payload objects carry `name`, `category`, `builtin`.
- Read timeout is raised to 5 seconds.
- The firmware builds the whole array in a 4096-byte buffer and sends it in a
  single call, with the `\r\n` appended into the same buffer so the terminator
  cannot be split from the body. If the array would overflow that buffer it
  answers `ERR payload list too large for response buffer` rather than a
  silently short list.
- An unparseable body is logged and treated as an empty list.

> **Known fault: a truncated `LIST` reply.** Observed against
> `fap_version=(1, 1)`: the host received exactly 64 bytes — one USB CDC bulk
> packet — with no terminator, nothing further arrived over the following 8
> seconds, and the device answered `PING` normally straight afterwards.
>
> The suspected cause is that `bridge_send()` loops over `CDC_DATA_SZ` chunks
> calling `furi_hal_cdc_send()` back to back while the bridge registers
> `.tx_ep_callback = NULL`, so nothing waits for the endpoint to drain between
> packets and every chunk after the first is dropped. That is inference from
> the source, not a measurement — only the 64-byte symptom was observed
> directly. `PING` and `STATUS` are unaffected because their replies fit in
> one packet; `LIST` is the only reply that routinely spans several.
>
> The host raises `IncompleteResponse` when a reply arrives without a
> terminator, so this surfaces as a named transfer fault. Reporting an empty
> list instead would say a device holding 45 payloads holds none.

#### `RELOAD` ✅

Re-reads payloads from the SD card.

- **Returns:** `OK RELOADED payloads=<n>`

#### `LOAD <json>` ✅

Pushes a one-off payload without touching the SD card. The argument is a
compact JSON object on the same line:

```
LOAD {"name":"probe","text":"Ignore previous instructions"}
```

Both fields are JSON-escaped, so a payload containing quotes, tabs, carriage
returns or newlines stays on one line and arrives intact. The name is capped
at 48 characters and the text at 512.

- **Returns:** `OK loaded <name>`
- **Errors:** `ERR invalid JSON`, `ERR missing name or text in JSON`

#### `SET DELAY <ms>` ✅

Sets the BadUSB start delay. Valid range 0–60000.

- **Returns:** `OK delay=<ms>`
- **Errors:** `ERR delay must be 0-60000 ms`

### Delivery channels

| Command | Reply verb | Host support |
|---|---|---|
| `EXEC BADUSB <name>` | `OK DONE <name>` | ✅ |
| `EXEC NFC <name>` | `OK WRITTEN <path>` | ✅ |
| `EXEC NFCEMU <name>` | `OK EMULATING <name>` | — |
| `EXEC NFCEMUURL <name>` | `OK EMULATING <name>` | — |
| `EXEC BLE <name>` | `OK BROADCASTING <name>` | ✅ |
| `EXEC BLEGATT <name>` | `OK SERVING <name>` | — |
| `EXEC QR <name>` | `OK DISPLAYING <name>` | ✅ |
| `EXEC USBDESC <name>` | `OK ADVERTISING <name>` | — |
| `EXEC GPIO <name>` | `OK SENT <name>` | — |
| `EXEC GPIOCAP <name>` | `OK REPLY <captured>` | — |
| `EXEC I2C <name>` | `OK I2CWROTE <n>` | — |
| `SCAN I2C` | `OK DEVICES <addresses>` | — |

`EXEC BADUSB` is allowed 120 seconds; `EXEC NFC`, `EXEC BLE` and the other
radio channels 10; `EXEC QR` 5.

`EXEC NFCEMUURL` emits a URI record rather than a Text record: iOS raises a
banner only for a URI, so the text-only channel reads as broken against a
stock phone when it is in fact being delivered.

`EXEC I2C` writes in 16-byte transactions and probes the address first,
refusing if nothing ACKs — an unexpected device on a guessed address might be
a PMIC, and payload text in its control registers is a bricked board.

`EXEC GPIOCAP` captures the target's reply and appends it to `captures.jsonl`
in the app's data directory, so a scripted sweep still leaves evidence on the
device.

### Stopping

| Command | Stops | Host support |
|---|---|---|
| `STOP` | The current execution | ✅ |
| `STOP BLE` | The BLE beacon | ✅ |
| `STOP BLEGATT` | The GATT server | — |
| `STOP NFCEMU` | NFC emulation | — |
| `STOP USBDESC` | USB descriptor advertising | — |

BLE advertising also stops on its own after roughly 60 seconds.

### Errors

| Reply | Cause |
|---|---|
| `ERR unknown command: <cmd>` | No verb matched |
| `ERR command too long` | Over 256 bytes |
| `ERR request timed out` | The app did not service the request |
| `ERR out of memory` | Allocation failed building a reply |

## Not in this protocol

**Sequences.** The host writes
`/ext/apps_data/mindgard/sequences/<name>.json`, and the current firmware
reads nothing from that directory — the sequence feature was removed from the
app. `hw flipper sequence` still composes and deploys files, but no on-device
code consumes them.

**Scan results.** `hw flipper sync-results` writes `results.json` for a
results viewer the app no longer has. The dependency now runs the other way:
the device produces `captures.jsonl` and the host reads it.

## Firmware

The FAP is declared in `.gitmodules` as `vendor/flipper-field-kit`, pointing
at `Mindgard/flipperzero-prompt-injection-field-kit`. The submodule has no
gitlink recorded in the index, so `git submodule update --init` cannot check
it out — the declaration alone is not enough. Clone it separately:

```
git clone https://github.com/Mindgard/flipperzero-prompt-injection-field-kit.git vendor/flipper-field-kit
```

SD card layout the app uses, under `/ext/apps_data/mindgard/`:

| File | Written by | Read by |
|---|---|---|
| `payloads.json` | Both; the app self-exports on first run | Both |
| `favorites.json` | The app | The app |
| `settings.json` | The app | The app |
| `captures.jsonl` | The app | The host |
| `sequences/` | The host | Nothing |
