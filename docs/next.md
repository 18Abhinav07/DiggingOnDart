# What I'll do next

The first weeks, if Dart will have me. Each step follows [`stage2.md`](stage2.md) and only starts once the one
before it has a measured answer.

1. **Run it on a base Air.** Run `./reproduce.sh` on an M1 or M2 to confirm or refute the small-Mac prediction
   (14B on the M4 Pro as a stand-in for 7B on a base chip), then take Metal GPU traces to check the
   kernel-length explanation directly.
2. **Measure in-process chunking.** Feed `llama_decode` k tokens per call and find out whether it closes the gap
   between the +23% of the HTTP-chunked version and the +11% of ubatch 64.
3. **Table and mode switch.** Build the per-device, per-model table and switch batch size on page weight, then
   check it against the success criteria on both machines.
4. **Controller, only if the table fails.** Follow the stop rule. Then point the same frame signal at
   speculative decoding, background embedding and CPU thread budgets.

— Abhinav Pangaria
