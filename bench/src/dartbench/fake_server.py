"""A stand-in for llama-server, used only by DARTBENCH_FAKE=1 dry runs and tests.

It speaks the same endpoints and streaming format, tokenises one token per character, and sleeps
for plausible (but heavily sped-up) prompt and decode times so every code path runs end to end.
The numbers it produces are not measurements.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SPEEDUP = 40.0  # fake runs finish quickly


def rates(model_key: str, ngl: int) -> tuple[float, float]:
    size = float(model_key.split("B-")[0])
    quant = model_key.split("-", 1)[1]
    bits = {"Q2_K": 2.6, "Q3_K_M": 3.4, "Q4_K_M": 4.8, "Q5_K_M": 5.7, "Q8_0": 8.5}.get(quant, 4.8)
    pp = 9000 / size * (1 if ngl else 0.12)
    tg = 2200 / (size * bits) * (1 if ngl else 0.45)
    return pp, tg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8089)
    ap.add_argument("--model", default="7B-Q4_K_M")
    ap.add_argument("--draft", default=None)
    ap.add_argument("--ngl", type=int, default=99)
    ap.add_argument("--ubatch", type=int, default=512)
    a = ap.parse_args()
    pp, tg = rates(a.model, a.ngl)
    rng = random.Random(1)
    cache = {"prompt": ""}
    time.sleep(0.3)  # "load"

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *x):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path.startswith("/health"):
                return self._json({"status": "ok"})
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/tokenize":
                return self._json({"tokens": [ord(c) for c in body.get("content", "")]})
            if self.path == "/detokenize":
                return self._json({"content": "".join(chr(t) for t in body.get("tokens", []))})
            if self.path == "/completion":
                return self._complete(body)
            self._json({"error": "not found"}, 404)

        def _complete(self, body):
            prompt = body["prompt"]
            n_pred = int(body.get("n_predict", 64))
            reuse = 0
            if body.get("cache_prompt"):
                p = cache["prompt"]
                while reuse < min(len(p), len(prompt)) and p[reuse] == prompt[reuse]:
                    reuse += 1
            cache["prompt"] = prompt
            new = len(prompt) - reuse
            prompt_s = new / pp * (1 + rng.gauss(0, 0.03))
            time.sleep(max(0.0, prompt_s / SPEEDUP))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def send(obj):
                b = f"data: {json.dumps(obj)}\n\n".encode()
                self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
                self.wfile.flush()

            n = n_pred if body.get("ignore_eos") else min(n_pred, rng.randint(n_pred // 2, n_pred))
            accept = None
            speed = tg
            if a.draft:
                accept = 0.7 if "Summarise" in prompt else 0.4
                speed = tg * (1 + 1.6 * accept) / 1.35
            t0 = time.time()
            for i in range(n):
                time.sleep(1 / speed / SPEEDUP)
                send({"content": "tok ", "stop": False})
            gen_s = (time.time() - t0) * SPEEDUP
            draft_n = int(n * 1.4) if a.draft else 0
            timings = {"prompt_n": new, "prompt_ms": prompt_s * 1000, "prompt_per_second": new / max(prompt_s, 1e-6),
                       "predicted_n": n, "predicted_ms": gen_s * 1000, "predicted_per_second": n / max(gen_s, 1e-6),
                       "cache_n": reuse}
            if a.draft:
                timings.update({"draft_n": draft_n, "draft_n_accepted": int(draft_n * accept)})
            send({"content": "", "stop": True, "stop_type": "limit" if n == n_pred else "eos", "timings": timings})
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
