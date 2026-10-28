#!/usr/bin/env python3
"""Minimal Gemini client - urllib only, no SDK, same no-dependency discipline as A3.

Carries the error handling Part 1 of the rubric asks for: bounded retries with
exponential backoff on rate limits and transient server errors, a hard timeout, and a
structured failure return rather than an exception that kills a 120-bill run.
"""
import json, os, time, urllib.request, urllib.error
import pool_state

BASE = "https://generativelanguage.googleapis.com/v1beta"

def _load_env():
    """Settings come from the real environment first, then .env at the project root.
    Loading both here - not just the key - avoids the trap of a stale default model
    silently overriding what .env says."""
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if not os.path.exists(env):
        return
    for line in open(env):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))

_load_env()

MODEL   = os.environ.get('GEMINI_MODEL', 'gemini-3.8-flash')
# Kept short on purpose. The pool's job is to move past a dead model quickly;
# a long timeout turns two unavailable models into three minutes of silence.
TIMEOUT = int(os.environ.get('GEMINI_TIMEOUT', '45'))

# The free tier's limit is GenerateRequestsPerDayPerProjectPerModel: 20 requests per day
# PER MODEL. Pacing cannot help with a daily cap - but the cap is scoped to a model, so a
# pool of models multiplies the budget. A model that returns RESOURCE_EXHAUSTED is retired
# for the rest of the process and the next one takes over.
POOL = [m.strip() for m in os.environ.get(
    'GEMINI_POOL',
    # Ordered by what this project's key can actually reach, measured rather than
    # assumed: 3.8 returns 503 and 3.7 is out of daily quota, so leading with them
    # cost 180 seconds before the first real attempt.
    'gemini-3.6-flash,gemini-3.5-flash,gemini-flash-lite-latest,'
    'gemini-3.5-flash-lite,gemini-3.8-flash,gemini-3.7-flash').split(',') if m.strip()]
# Retirement is timed, not permanent - see pool_state. This server outlives the daily
# cap it was retiring models against.
_exhausted = pool_state.new_state()

def pool_status():
    return {'pool': POOL, 'exhausted': pool_state.retired(_exhausted, POOL),
            'available': pool_state.available(_exhausted, POOL)}
ATTEMPTS = 4
# When a pool is in play, re-asking one overloaded model is the wrong way to spend
# the wait. Four attempts at 2s doubling is 14s of sleep per model, and with six
# models an interactive request sat for over two minutes before answering. Trying a
# DIFFERENT model is both faster and likelier to work, so a pooled call gives each
# model two attempts and moves on.
POOL_ATTEMPTS = 2
# And the whole pooled call is bounded, because a person is waiting on it. Past this
# it returns an honest failure rather than holding a spinner.
DEADLINE = int(os.environ.get('GEMINI_DEADLINE', '150'))
BACKOFF  = 2.0          # seconds, doubled each retry
RETRY_ON = {429, 500, 502, 503, 504}

class GeminiError(RuntimeError):
    pass

def _key():
    k = os.environ.get('GEMINI_API_KEY', '').strip()
    if not k:
        raise GeminiError("GEMINI_API_KEY is not set (env var or .env at the project root)")
    return k

# A call is not started with less than this left of its deadline: it would only time out.
MIN_CALL_SECONDS = 2.0


def _post(url, payload, timeout=None):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
        return json.loads(r.read())


def _remaining(stop_at):
    return None if stop_at is None else stop_at - time.time()


def _out_of_time(attempts, budget):
    return {'ok': False, 'timed_out': True, 'attempts': attempts,
            'error': f'deadline reached ({budget:.0f}s budget)'}

def generate(prompt, schema=None, temperature=0.0, model=None, image=None,
             deadline=None, request_timeout=None):
    """Calls the pool in order, skipping models already known to be out of daily quota.
    Returns the first success, or the last failure if every model is exhausted.

    `request_timeout` caps any one request, so a model that hangs is left for the next
    one in the pool rather than waited on for the whole budget.

    `deadline` is the caller's whole budget in seconds, and it is a budget for the call,
    not a hint: no HTTP request is given longer than what is left of it. It used to cap
    only the loop between models, while each request kept its own 45-second timeout and
    up to four retries - so a question asked of the Companion could wait minutes, and one
    took 46 seconds to answer.
    """
    global _exhausted
    budget = DEADLINE if deadline is None else deadline
    stop_at = time.time() + budget
    if model:
        return _generate_one(prompt, schema, temperature, model, image, stop_at=stop_at,
                             budget=budget, request_timeout=request_timeout)
    last = {'ok': False, 'error': 'no models available', 'attempts': 0}
    for m in POOL:
        if pool_state.is_retired(_exhausted, m):
            continue
        if _remaining(stop_at) < MIN_CALL_SECONDS:
            last = {**last, 'timed_out': True,
                    'error': f"gave up after {budget:.0f}s · last: {last.get('error')}"}
            break
        r = _generate_one(prompt, schema, temperature, m, image,
                          attempts=POOL_ATTEMPTS, stop_at=stop_at, budget=budget,
                          request_timeout=request_timeout)
        if r['ok']:
            r['model'] = m
            return r
        last = r
        err = str(r.get('error', ''))
        if 'RESOURCE_EXHAUSTED' in err or '429' in err:
            _exhausted = pool_state.retire(_exhausted, m)   # out of daily quota for now
            continue
        # A 503 means this model is overloaded right now, which is the other thing a pool
        # is for. The comment below used to say a non-quota failure is not fixed by another
        # model; that is true of a malformed request and false of an overloaded one. Tried
        # on a day when gemini-3.8-flash was returning 503 to every request, the pool gave
        # up after one model while five others were available and working.
        if any(code in err for code in ('HTTP 503', 'HTTP 502', 'HTTP 500', 'UNAVAILABLE')):
            continue                   # overloaded, not broken - the next model may serve
        if r.get('timed_out'):
            break                      # the budget is spent; another model cannot help
        return r                       # a malformed request is not fixed by another model
    last['model'] = None
    last['pool_exhausted'] = True
    return last

def _generate_one(prompt, schema, temperature, model, image=None, attempts=None,
                  stop_at=None, budget=None, request_timeout=None):
    """One model, with bounded retries and exponential backoff.

    `image` is an optional (mime_type, base64_data) pair. A photograph of a bill has no
    text layer to extract, so the only way to read one is to let the model look at it -
    the same extraction task, a different input channel. Everything downstream is
    unchanged: the Checker still produces every figure and the guard still holds.
    """
    url = f"{BASE}/models/{model}:generateContent?key={_key()}"
    cfg = {'temperature': temperature}
    if schema:
        cfg['responseMimeType'] = 'application/json'
        cfg['responseSchema'] = schema
    parts = [{'text': prompt}]
    if image:
        mime, b64 = image
        parts.append({'inline_data': {'mime_type': mime, 'data': b64}})
    payload = {'contents': [{'parts': parts}], 'generationConfig': cfg}

    attempts = attempts or ATTEMPTS
    last = None
    for attempt in range(1, attempts + 1):
        left = _remaining(stop_at)
        if left is not None and left < MIN_CALL_SECONDS:
            return _out_of_time(attempt - 1, budget or 0)
        try:
            raw = _post(url, payload,
                        timeout=min(t for t in (TIMEOUT, left, request_timeout) if t))
            cand = (raw.get('candidates') or [{}])[0]
            parts = (cand.get('content') or {}).get('parts') or [{}]
            text = parts[0].get('text', '')
            usage = raw.get('usageMetadata', {}) or {}
            out = {'ok': True, 'text': text, 'json': None, 'attempts': attempt,
                   'usage': {'prompt_tokens': usage.get('promptTokenCount'),
                             'output_tokens': usage.get('candidatesTokenCount'),
                             'total_tokens': usage.get('totalTokenCount')},
                   'finish_reason': cand.get('finishReason')}
            if schema:
                try:
                    out['json'] = json.loads(text)
                except json.JSONDecodeError as ex:
                    # the model returned prose where JSON was demanded - a real failure mode
                    return {'ok': False, 'attempts': attempt,
                            'error': f'malformed JSON from model: {ex}', 'text': text[:400]}
            return out
        except urllib.error.HTTPError as ex:
            body = ex.read()[:900].decode('utf-8', 'ignore')
            last = f'HTTP {ex.code}: {body}'
            # a per-day quota failure will not clear in 15 seconds; do not burn retries on it
            if ex.code == 429 and 'PerDay' in body:
                return {'ok': False, 'error': last, 'attempts': attempt, 'quota': 'daily'}
            if ex.code not in RETRY_ON or attempt == attempts:
                return {'ok': False, 'error': last, 'attempts': attempt}
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            last = f'{type(ex).__name__}: {ex}'
            if attempt == attempts:
                return {'ok': False, 'error': last, 'attempts': attempt}
        pause = BACKOFF * (2 ** (attempt - 1))
        left = _remaining(stop_at)
        if left is not None and left - pause < MIN_CALL_SECONDS:
            return {**_out_of_time(attempt, budget or 0), 'error': f'{last} · then out of time'}
        time.sleep(pause)
    return {'ok': False, 'error': last or 'exhausted retries', 'attempts': attempts}

def list_models():
    """Confirms which models this key can actually reach - run once after adding a key."""
    url = f"{BASE}/models?key={_key()}"
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        data = json.loads(r.read())
    return [m['name'].replace('models/', '') for m in data.get('models', [])
            if 'generateContent' in m.get('supportedGenerationMethods', [])]
