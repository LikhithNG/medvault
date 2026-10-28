#!/usr/bin/env python3
"""Groq client - same contract as gemini.py, so the Reader does not change.

Groq is OpenAI-compatible, so structured output comes from JSON mode plus the schema
restated in the prompt, rather than Gemini's responseSchema field. The daily allowance is
in the thousands rather than Gemini free tier's 20 per model, which is the entire reason
for this module's existence.
"""
import json, os, time, urllib.request, urllib.error
import pool_state

BASE = "https://api.groq.com/openai/v1/chat/completions"
# Groq sits behind Cloudflare, which rejects urllib's default agent with error 1010.
# Identify the client properly rather than letting it look like an unnamed bot.
UA = "medvault/1.0 (INFO7375 coursework; python-urllib)"

def _load_env():
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if not os.path.exists(env):
        return
    for line in open(env):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"\''))

_load_env()

MODEL    = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
TIMEOUT  = int(os.environ.get('GROQ_TIMEOUT', '60'))
ATTEMPTS = 4
BACKOFF  = 2.0
RETRY_ON = {429, 500, 502, 503, 504}

POOL = [m.strip() for m in os.environ.get(
    'GROQ_POOL', 'llama-3.3-70b-versatile,llama-3.1-8b-instant,'
                 'meta-llama/llama-4-scout-17b-16e-instruct').split(',') if m.strip()]
# Retirement is timed, not permanent - see pool_state.
_exhausted = pool_state.new_state()

class GroqError(RuntimeError):
    pass

def pool_status():
    return {'pool': POOL, 'exhausted': pool_state.retired(_exhausted, POOL),
            'available': pool_state.available(_exhausted, POOL)}

def _key():
    k = os.environ.get('GROQ_API_KEY', '').strip()
    if not k:
        raise GroqError("GROQ_API_KEY is not set (env var or .env at the project root)")
    return k

MIN_CALL_SECONDS = 2.0      # see gemini.py: a call is not started that can only time out


def _post(payload, timeout=None):
    req = urllib.request.Request(
        BASE, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': UA,
                 'Accept': 'application/json',
                 'Authorization': f'Bearer {_key()}'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
        return json.loads(r.read())


def _out_of_time(attempts, budget):
    return {'ok': False, 'timed_out': True, 'attempts': attempts,
            'error': f'deadline reached ({budget:.0f}s budget)'}

def _one(prompt, schema, temperature, model, stop_at=None, budget=None):
    body = {'model': model, 'temperature': temperature,
            'messages': [{'role': 'user', 'content': prompt}]}
    if schema:
        body['response_format'] = {'type': 'json_object'}

    last = None
    for attempt in range(1, ATTEMPTS + 1):
        left = None if stop_at is None else stop_at - time.time()
        if left is not None and left < MIN_CALL_SECONDS:
            return _out_of_time(attempt - 1, budget or 0)
        try:
            raw = _post(body, timeout=min(TIMEOUT, left) if left else None)
            choice = (raw.get('choices') or [{}])[0]
            text = ((choice.get('message') or {}).get('content')) or ''
            u = raw.get('usage') or {}
            out = {'ok': True, 'text': text, 'json': None, 'attempts': attempt,
                   'usage': {'prompt_tokens': u.get('prompt_tokens'),
                             'output_tokens': u.get('completion_tokens'),
                             'total_tokens': u.get('total_tokens')},
                   'finish_reason': choice.get('finish_reason')}
            if schema:
                try:
                    out['json'] = json.loads(text)
                except json.JSONDecodeError as ex:
                    return {'ok': False, 'attempts': attempt,
                            'error': f'malformed JSON from model: {ex}', 'text': text[:400]}
            return out
        except urllib.error.HTTPError as ex:
            body_txt = ex.read()[:900].decode('utf-8', 'ignore')
            last = f'HTTP {ex.code}: {body_txt}'
            # a per-day quota failure will not clear during a backoff window
            if ex.code == 429 and ('per day' in body_txt.lower() or 'rpd' in body_txt.lower()):
                return {'ok': False, 'error': last, 'attempts': attempt, 'quota': 'daily'}
            if ex.code not in RETRY_ON or attempt == ATTEMPTS:
                return {'ok': False, 'error': last, 'attempts': attempt}
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            last = f'{type(ex).__name__}: {ex}'
            if attempt == ATTEMPTS:
                return {'ok': False, 'error': last, 'attempts': attempt}
        pause = BACKOFF * (2 ** (attempt - 1))
        if stop_at is not None and stop_at - time.time() - pause < MIN_CALL_SECONDS:
            return {**_out_of_time(attempt, budget or 0), 'error': f'{last} · then out of time'}
        time.sleep(pause)
    return {'ok': False, 'error': last or 'exhausted retries', 'attempts': ATTEMPTS}

def generate(prompt, schema=None, temperature=0.0, model=None, deadline=None):
    """Calls the pool in order, retiring any model that reports a daily quota failure.

    `deadline` is the caller's whole budget in seconds; no request outlasts it.
    """
    global _exhausted
    stop_at = None if deadline is None else time.time() + deadline
    if model:
        return _one(prompt, schema, temperature, model, stop_at, deadline)
    last = {'ok': False, 'error': 'no models available', 'attempts': 0}
    for m in POOL:
        if pool_state.is_retired(_exhausted, m):
            continue
        if stop_at is not None and stop_at - time.time() < MIN_CALL_SECONDS:
            return {**last, 'timed_out': True, 'model': None,
                    'error': f"gave up after {deadline:.0f}s · last: {last.get('error')}"}
        r = _one(prompt, schema, temperature, m, stop_at, deadline)
        if r['ok']:
            r['model'] = m
            return r
        last = r
        if r.get('quota') == 'daily':
            _exhausted = pool_state.retire(_exhausted, m)
            continue
        return r
    last['model'] = None
    last['pool_exhausted'] = True
    return last

def list_models():
    req = urllib.request.Request('https://api.groq.com/openai/v1/models',
                                 headers={'Authorization': f'Bearer {_key()}',
                                          'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return [m['id'] for m in json.loads(r.read()).get('data', [])]
