# Stdio adapter design

The host launches one Python MCP server per stdio connection. The adapter holds the attached session ID and the observation ID associated with the last PNG it returned. The Rust CLI is the adapter's only runtime backend. Validation, capture, compositor identity checks, input serialization, request deduplication and device cleanup remain in the owner.

Start and observe return a text metadata block and an image block containing the original PNG bytes. An ordinary action pins the last delivered observation and generates a new request ID. The adapter clears its observation before dispatch and replaces it only after reading a successful screenshot. Other clients can invalidate the observation. Recovery requires observing again; replay after a lost reply is a caller decision.

Read-only UI queries use the CLI's AT-SPI discovery commands. They return window identity, output and nodes without advancing the observation. The caller must compare the output and point with its current screenshot before acting. Start, observe and act reject overlapping requests within one adapter. Stop can interrupt action execution and pins the attached session ID.

An orderly disconnect requests cleanup only for an owner created by this adapter. Abrupt disconnects rely on the owner's idle timeout. Explicit stop also applies to an attached owner. No network listener or separate capture pipeline is needed.

The private integration probe uses official stdio clients to exercise attachment, stale observation rejection, UI discovery, inline PNG byte equality, real input, and cleanup. The separate latest-race probe interposes at the CLI socket boundary, advances the real owner's observation after it answers status, then forwards the obsolete action unchanged.

Lifecycle verification on private Wayfire covered three shutdown paths. An explicit stop during real GTK text delivery returned ACTION_CANCELLED and the partially typed string stopped changing. Closing an owning SDK client normally removed its PNG and control socket. Killing only a dedicated stdio adapter left the same owner active immediately afterward, then its configured three-second idle timeout removed the PNG and socket. Closing an attached second client also left the original session usable.
